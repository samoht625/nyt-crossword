(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.PuzReader = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const HEADER_LENGTH = 0x34;
  const BLOCK_CHARACTERS = new Set([".", ":"]);

  function decode(bytes) {
    try {
      return new TextDecoder("windows-1252").decode(bytes);
    } catch (_error) {
      return Array.from(bytes, (value) => String.fromCharCode(value)).join("");
    }
  }

  function readString(bytes, start) {
    let end = start;
    while (end < bytes.length && bytes[end] !== 0) {
      end += 1;
    }
    if (end >= bytes.length) {
      throw new Error("The puzzle has an unterminated text field.");
    }
    return {
      value: decode(bytes.subarray(start, end)),
      next: end + 1,
    };
  }

  function isBlock(character) {
    return BLOCK_CHARACTERS.has(character);
  }

  function makeEntry({
    id,
    direction,
    number,
    start,
    width,
    height,
    solution,
    clue,
  }) {
    const cells = [];
    let index = start;
    const step = direction === "Across" ? 1 : width;

    while (
      index < solution.length &&
      !isBlock(solution[index]) &&
      (direction === "Down" || Math.floor(index / width) === Math.floor(start / width))
    ) {
      cells.push(index);
      index += step;
      if (direction === "Down" && Math.floor(index / width) >= height) {
        break;
      }
    }

    return {
      id,
      direction,
      number,
      clue,
      cells,
      answer: cells.map((cell) => solution[cell]).join(""),
    };
  }

  function parse(input) {
    const bytes =
      input instanceof Uint8Array
        ? input
        : input instanceof ArrayBuffer
          ? new Uint8Array(input)
          : null;

    if (!bytes || bytes.length < HEADER_LENGTH) {
      throw new Error("This is not a valid .puz file.");
    }

    const magic = decode(bytes.subarray(2, 13));
    if (magic !== "ACROSS&DOWN") {
      throw new Error("This file is not in Across Lite .puz format.");
    }

    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const width = bytes[0x2c];
    const height = bytes[0x2d];
    const clueCount = view.getUint16(0x2e, true);
    const cellCount = width * height;
    const gridEnd = HEADER_LENGTH + cellCount * 2;

    if (!width || !height || gridEnd > bytes.length) {
      throw new Error("The .puz grid dimensions are invalid.");
    }

    const solution = decode(bytes.subarray(HEADER_LENGTH, HEADER_LENGTH + cellCount))
      .toUpperCase()
      .split("");
    const savedFill = decode(bytes.subarray(HEADER_LENGTH + cellCount, gridEnd))
      .toUpperCase()
      .split("");

    let cursor = gridEnd;
    const titleField = readString(bytes, cursor);
    cursor = titleField.next;
    const authorField = readString(bytes, cursor);
    cursor = authorField.next;
    const copyrightField = readString(bytes, cursor);
    cursor = copyrightField.next;

    const clueTexts = [];
    for (let index = 0; index < clueCount; index += 1) {
      const field = readString(bytes, cursor);
      clueTexts.push(field.value);
      cursor = field.next;
    }

    let notes = "";
    if (cursor < bytes.length) {
      try {
        notes = readString(bytes, cursor).value;
      } catch (_error) {
        notes = "";
      }
    }

    const cells = solution.map((character, index) => ({
      index,
      row: Math.floor(index / width),
      column: index % width,
      block: isBlock(character),
      number: null,
      across: null,
      down: null,
    }));
    const entries = [];
    const across = [];
    const down = [];
    let nextNumber = 1;
    let clueIndex = 0;

    for (let row = 0; row < height; row += 1) {
      for (let column = 0; column < width; column += 1) {
        const index = row * width + column;
        if (cells[index].block) {
          continue;
        }

        const startsAcross =
          (column === 0 || cells[index - 1].block) &&
          column + 1 < width &&
          !cells[index + 1].block;
        const startsDown =
          (row === 0 || cells[index - width].block) &&
          row + 1 < height &&
          !cells[index + width].block;

        if (!startsAcross && !startsDown) {
          continue;
        }

        const number = nextNumber;
        nextNumber += 1;
        cells[index].number = number;

        if (startsAcross) {
          const entry = makeEntry({
            id: `A${number}`,
            direction: "Across",
            number,
            start: index,
            width,
            height,
            solution,
            clue: clueTexts[clueIndex] ?? "",
          });
          clueIndex += 1;
          entries.push(entry);
          across.push(entry);
          for (const cellIndex of entry.cells) {
            cells[cellIndex].across = entry.id;
          }
        }

        if (startsDown) {
          const entry = makeEntry({
            id: `D${number}`,
            direction: "Down",
            number,
            start: index,
            width,
            height,
            solution,
            clue: clueTexts[clueIndex] ?? "",
          });
          clueIndex += 1;
          entries.push(entry);
          down.push(entry);
          for (const cellIndex of entry.cells) {
            cells[cellIndex].down = entry.id;
          }
        }
      }
    }

    if (clueIndex !== clueCount) {
      throw new Error(
        `The grid defines ${clueIndex} answers, but the file contains ${clueCount} clues.`,
      );
    }

    const initialFill = savedFill.map((character, index) => {
      if (cells[index].block) {
        return "";
      }
      return /^[A-Z]$/.test(character) ? character : "";
    });

    return {
      title: titleField.value || "Untitled Crossword",
      author: authorField.value,
      copyright: copyrightField.value,
      notes,
      width,
      height,
      solution,
      initialFill,
      cells,
      entries,
      across,
      down,
      entryMap: Object.fromEntries(entries.map((entry) => [entry.id, entry])),
      checksum: view.getUint16(0, true).toString(16).padStart(4, "0"),
      scrambled: view.getUint16(0x32, true) !== 0,
    };
  }

  return { parse };
});
