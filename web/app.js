(function () {
  "use strict";

  const elements = {
    puzzleList: document.querySelector("#puzzle-list"),
    libraryStatus: document.querySelector("#library-status"),
    welcome: document.querySelector("#welcome"),
    solver: document.querySelector("#solver"),
    galleryButton: document.querySelector("#gallery-button"),
    title: document.querySelector("#puzzle-title"),
    author: document.querySelector("#puzzle-author"),
    timer: document.querySelector("#timer"),
    grid: document.querySelector("#grid"),
    currentClue: document.querySelector("#current-clue"),
    acrossClues: document.querySelector("#across-clues"),
    downClues: document.querySelector("#down-clues"),
    checkButton: document.querySelector("#check-button"),
    revealButton: document.querySelector("#reveal-button"),
    resetButton: document.querySelector("#reset-button"),
    keyboardInput: document.querySelector("#keyboard-input"),
    toast: document.querySelector("#toast"),
  };

  const canonicalHomePath = window.location.pathname.endsWith("/index.html")
    ? window.location.pathname.slice(0, -"index.html".length) || "/"
    : window.location.pathname;
  if (canonicalHomePath !== window.location.pathname) {
    window.history.replaceState(
      null,
      "",
      `${canonicalHomePath}${window.location.search}${window.location.hash}`,
    );
  }

  let state = null;
  let timerInterval = null;
  let toastTimeout = null;

  function showToast(message) {
    elements.toast.textContent = message;
    elements.toast.classList.add("visible");
    window.clearTimeout(toastTimeout);
    toastTimeout = window.setTimeout(() => {
      elements.toast.classList.remove("visible");
    }, 2800);
  }

  function focusForTyping() {
    if (window.matchMedia("(pointer: coarse)").matches) {
      elements.keyboardInput.value = "";
      elements.keyboardInput.focus({ preventScroll: true });
    } else {
      elements.grid.focus({ preventScroll: true });
    }
  }

  function storageKey(puzzle) {
    return [
      "tido-crossword",
      puzzle.checksum,
      `${puzzle.width}x${puzzle.height}`,
      puzzle.title,
      puzzle.author,
    ].join(":");
  }

  function readProgress(key, puzzle) {
    try {
      const saved = JSON.parse(localStorage.getItem(key));
      const validValues =
        Array.isArray(saved?.values) &&
        saved.values.length === puzzle.cells.length &&
        saved.values.every((value) => value === "" || /^[A-Z]$/.test(value));
      if (!validValues) {
        return null;
      }
      return saved;
    } catch (_error) {
      return null;
    }
  }

  function elapsedSeconds() {
    if (!state) {
      return 0;
    }
    const currentRun =
      state.running && state.timerStartedAt
        ? Math.floor((Date.now() - state.timerStartedAt) / 1000)
        : 0;
    return state.elapsedBase + currentRun;
  }

  function saveProgress() {
    if (!state) {
      return;
    }
    const payload = {
      values: state.values,
      revealed: Array.from(state.revealed),
      elapsed: elapsedSeconds(),
      complete: state.complete,
    };
    try {
      localStorage.setItem(state.storageKey, JSON.stringify(payload));
    } catch (_error) {
      // Some browsers disable storage for pages opened from the filesystem.
    }
  }

  function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainder = seconds % 60;
    if (hours) {
      return `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
    }
    return `${minutes}:${String(remainder).padStart(2, "0")}`;
  }

  function updateTimer() {
    elements.timer.textContent = formatTime(elapsedSeconds());
  }

  function startTimerLoop() {
    window.clearInterval(timerInterval);
    updateTimer();
    timerInterval = window.setInterval(() => {
      updateTimer();
      if (state?.running && elapsedSeconds() % 10 === 0) {
        saveProgress();
      }
    }, 1000);
  }

  function createClueList(entries, container) {
    const fragment = document.createDocumentFragment();
    for (const entry of entries) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const number = document.createElement("span");
      const text = document.createElement("span");

      button.type = "button";
      button.className = "clue-button";
      button.id = `clue-${entry.id}`;
      button.dataset.entryId = entry.id;
      number.className = "clue-number";
      number.textContent = entry.number;
      text.textContent = entry.clue;
      button.append(number, text);
      button.addEventListener("click", () => {
        selectEntry(entry.id);
        focusForTyping();
      });
      item.append(button);
      fragment.append(item);
    }
    container.replaceChildren(fragment);
  }

  function renderPuzzle() {
    const { puzzle } = state;
    elements.title.textContent = puzzle.title;
    elements.author.textContent = puzzle.author ? `By ${puzzle.author}` : "";
    elements.grid.style.setProperty("--columns", puzzle.width);
    elements.grid.style.setProperty("--rows", puzzle.height);
    elements.grid.setAttribute(
      "aria-label",
      `${puzzle.title}, ${puzzle.width} by ${puzzle.height} crossword grid`,
    );

    const fragment = document.createDocumentFragment();
    for (const cell of puzzle.cells) {
      if (cell.block) {
        const block = document.createElement("div");
        block.className = "cell block";
        block.setAttribute("aria-hidden", "true");
        fragment.append(block);
        continue;
      }

      const button = document.createElement("button");
      const number = document.createElement("span");
      const letter = document.createElement("span");
      button.type = "button";
      button.className = "cell";
      button.dataset.index = cell.index;
      button.tabIndex = -1;
      button.setAttribute("role", "gridcell");
      button.setAttribute(
        "aria-label",
        `Row ${cell.row + 1}, column ${cell.column + 1}${cell.number ? `, ${cell.number}` : ""}`,
      );
      number.className = "cell-number";
      number.textContent = cell.number || "";
      letter.className = "letter";
      button.append(number, letter);
      button.addEventListener("click", () => {
        selectCell(cell.index, null, true);
        focusForTyping();
      });
      fragment.append(button);
    }
    elements.grid.replaceChildren(fragment);

    createClueList(puzzle.across, elements.acrossClues);
    createClueList(puzzle.down, elements.downClues);
    document.body.classList.add("is-solving");
    elements.welcome.hidden = true;
    elements.solver.hidden = false;
    window.scrollTo({ top: 0, behavior: "auto" });
    updateGrid();
  }

  function entryForCell(index, direction) {
    const cell = state.puzzle.cells[index];
    const id = direction === "Across" ? cell.across : cell.down;
    return id ? state.puzzle.entryMap[id] : null;
  }

  function selectCell(index, requestedDirection = null, toggle = false) {
    const cell = state?.puzzle.cells[index];
    if (!cell || cell.block) {
      return;
    }

    let direction = requestedDirection || state.direction;
    const hasAcross = Boolean(cell.across);
    const hasDown = Boolean(cell.down);

    if (toggle && index === state.selected && hasAcross && hasDown) {
      direction = state.direction === "Across" ? "Down" : "Across";
    } else if (!entryForCell(index, direction)) {
      direction = hasAcross ? "Across" : "Down";
    }

    state.selected = index;
    state.direction = direction;
    state.activeEntryId =
      direction === "Across" ? cell.across || cell.down : cell.down || cell.across;
    if (!state.activeEntryId) {
      return;
    }
    state.direction = state.puzzle.entryMap[state.activeEntryId].direction;
    updateSelection();
  }

  function selectEntry(entryId, preferBlank = true) {
    const entry = state?.puzzle.entryMap[entryId];
    if (!entry) {
      return;
    }
    state.direction = entry.direction;
    state.activeEntryId = entry.id;
    state.selected =
      (preferBlank && entry.cells.find((index) => !state.values[index])) || entry.cells[0];
    updateSelection();
  }

  function updateSelection() {
    if (!state) {
      return;
    }
    const activeEntry = state.puzzle.entryMap[state.activeEntryId];
    const activeCells = new Set(activeEntry?.cells || []);

    for (const button of elements.grid.querySelectorAll(".cell:not(.block)")) {
      const index = Number(button.dataset.index);
      button.classList.toggle("in-word", activeCells.has(index));
      button.classList.toggle("selected", index === state.selected);
      button.setAttribute("aria-selected", index === state.selected ? "true" : "false");
    }

    for (const button of document.querySelectorAll(".clue-button")) {
      button.classList.toggle("active", button.dataset.entryId === state.activeEntryId);
    }

    if (activeEntry) {
      const number = document.createElement("span");
      const clue = document.createElement("span");
      number.className = "current-clue-number";
      number.textContent = `${activeEntry.number}${activeEntry.direction[0]}`;
      clue.textContent = activeEntry.clue;
      elements.currentClue.replaceChildren(number, clue);
      if (window.matchMedia("(min-width: 1041px)").matches) {
        document
          .querySelector(`#clue-${activeEntry.id}`)
          ?.scrollIntoView({ block: "nearest" });
      }
    }
  }

  function updateGrid() {
    if (!state) {
      return;
    }
    for (const button of elements.grid.querySelectorAll(".cell:not(.block)")) {
      const index = Number(button.dataset.index);
      button.querySelector(".letter").textContent = state.values[index];
      button.classList.toggle("wrong", state.wrong.has(index));
      button.classList.toggle("revealed", state.revealed.has(index));
    }
    updateSelection();
  }

  function nextEntry(step) {
    const entries =
      state.direction === "Across" ? state.puzzle.across : state.puzzle.down;
    const currentIndex = entries.findIndex((entry) => entry.id === state.activeEntryId);
    const nextIndex = (currentIndex + step + entries.length) % entries.length;
    selectEntry(entries[nextIndex].id);
  }

  function advanceWithinEntry(step) {
    const entry = state.puzzle.entryMap[state.activeEntryId];
    const position = entry.cells.indexOf(state.selected);
    const nextPosition = position + step;
    if (nextPosition >= 0 && nextPosition < entry.cells.length) {
      selectCell(entry.cells[nextPosition], entry.direction);
    } else {
      nextEntry(step > 0 ? 1 : -1);
    }
  }

  function advanceAfterLetter() {
    const entry = state.puzzle.entryMap[state.activeEntryId];
    const position = entry.cells.indexOf(state.selected);

    // Match the NYT defaults: skip filled squares, then wrap to the first
    // blank in this answer before advancing to the next clue.
    for (let offset = 1; offset < entry.cells.length; offset += 1) {
      const index = entry.cells[(position + offset) % entry.cells.length];
      if (!state.values[index]) {
        selectCell(index, entry.direction);
        return;
      }
    }

    nextEntry(1);
  }

  function enterLetter(letter) {
    resumeTimerIfNeeded();
    state.values[state.selected] = letter;
    state.wrong.delete(state.selected);
    updateGrid();
    saveProgress();
    if (!finishIfComplete()) {
      advanceAfterLetter();
    }
  }

  function eraseLetter() {
    resumeTimerIfNeeded();
    if (state.values[state.selected]) {
      state.values[state.selected] = "";
      state.wrong.delete(state.selected);
      updateGrid();
    } else {
      advanceWithinEntry(-1);
      state.values[state.selected] = "";
      state.wrong.delete(state.selected);
      updateGrid();
    }
    saveProgress();
  }

  function moveSpatial(rowChange, columnChange, direction) {
    const { puzzle } = state;
    const selected = puzzle.cells[state.selected];
    if (state.direction !== direction && entryForCell(state.selected, direction)) {
      selectCell(state.selected, direction);
      return;
    }
    let row = selected.row + rowChange;
    let column = selected.column + columnChange;
    while (row >= 0 && row < puzzle.height && column >= 0 && column < puzzle.width) {
      const index = row * puzzle.width + column;
      if (!puzzle.cells[index].block) {
        selectCell(index, direction);
        return;
      }
      row += rowChange;
      column += columnChange;
    }
  }

  function switchDirection() {
    const cell = state.puzzle.cells[state.selected];
    if (cell.across && cell.down) {
      selectCell(
        state.selected,
        state.direction === "Across" ? "Down" : "Across",
      );
    }
  }

  function resumeTimerIfNeeded() {
    if (!state.complete) {
      return;
    }
    state.complete = false;
    state.running = true;
    state.timerStartedAt = Date.now();
  }

  function finishIfComplete() {
    const openCells = state.puzzle.cells.filter((cell) => !cell.block);
    const isFilled = openCells.every((cell) => state.values[cell.index]);
    const isCorrect =
      isFilled &&
      openCells.every(
        (cell) => state.values[cell.index] === state.puzzle.solution[cell.index],
      );
    if (!isCorrect) {
      return false;
    }

    const wasComplete = state.complete;
    state.elapsedBase = elapsedSeconds();
    state.timerStartedAt = null;
    state.running = false;
    state.complete = true;
    state.wrong.clear();
    updateGrid();
    updateTimer();
    saveProgress();
    if (!wasComplete) {
      showToast(`Solved in ${formatTime(state.elapsedBase)}. Nice work!`);
    }
    return true;
  }

  function checkPuzzle() {
    state.wrong.clear();
    let emptyCount = 0;
    for (const cell of state.puzzle.cells) {
      if (cell.block) {
        continue;
      }
      if (!state.values[cell.index]) {
        emptyCount += 1;
      } else if (state.values[cell.index] !== state.puzzle.solution[cell.index]) {
        state.wrong.add(cell.index);
      }
    }
    updateGrid();

    if (state.wrong.size) {
      showToast(
        `${state.wrong.size} incorrect ${state.wrong.size === 1 ? "square" : "squares"}.`,
      );
    } else if (emptyCount) {
      showToast("Everything filled so far is correct.");
    } else {
      finishIfComplete();
    }
  }

  function revealWord() {
    const entry = state.puzzle.entryMap[state.activeEntryId];
    if (!entry || !window.confirm(`Reveal ${entry.number} ${entry.direction}?`)) {
      return;
    }
    for (const index of entry.cells) {
      state.values[index] = state.puzzle.solution[index];
      state.revealed.add(index);
      state.wrong.delete(index);
    }
    updateGrid();
    saveProgress();
    finishIfComplete();
  }

  function resetPuzzle() {
    if (!window.confirm("Clear your answers and reset the timer?")) {
      return;
    }
    state.values = state.puzzle.initialFill.slice();
    state.wrong.clear();
    state.revealed.clear();
    state.complete = false;
    state.elapsedBase = 0;
    state.timerStartedAt = Date.now();
    state.running = true;
    selectEntry(state.puzzle.entries[0].id);
    updateGrid();
    updateTimer();
    saveProgress();
    showToast("Puzzle reset.");
  }

  async function loadPuzzleBuffer(buffer) {
    try {
      const puzzle = window.PuzReader.parse(buffer);
      if (puzzle.scrambled) {
        throw new Error("Scrambled/encrypted .puz solutions are not supported.");
      }

      const key = storageKey(puzzle);
      const saved = readProgress(key, puzzle);
      const values = saved?.values?.slice() || puzzle.initialFill.slice();
      const complete = Boolean(
        saved?.complete &&
          puzzle.cells
            .filter((cell) => !cell.block)
            .every((cell) => values[cell.index] === puzzle.solution[cell.index]),
      );
      state = {
        puzzle,
        storageKey: key,
        values,
        revealed: new Set(saved?.revealed || []),
        wrong: new Set(),
        selected: null,
        direction: "Across",
        activeEntryId: null,
        elapsedBase: Number.isFinite(saved?.elapsed) ? saved.elapsed : 0,
        timerStartedAt: complete ? null : Date.now(),
        running: !complete,
        complete,
      };

      renderPuzzle();
      const firstEntry =
        puzzle.entries.find((entry) =>
          entry.cells.some((index) => !state.values[index]),
        ) || puzzle.entries[0];
      selectEntry(firstEntry.id);
      startTimerLoop();
      focusForTyping();
      if (saved) {
        showToast(complete ? "Completed puzzle restored." : "Saved progress restored.");
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Could not open that puzzle.");
    }
  }

  async function loadPuzzleUrl(url) {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Could not load puzzle (${response.status}).`);
      }
      await loadPuzzleBuffer(await response.arrayBuffer());
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Could not load that puzzle.");
    }
  }

  function showGallery() {
    if (state) {
      state.elapsedBase = elapsedSeconds();
      state.timerStartedAt = null;
      state.running = false;
      saveProgress();
    }
    window.history.replaceState(null, "", canonicalHomePath);
    elements.keyboardInput.blur();
    elements.keyboardInput.value = "";
    document.body.classList.remove("is-solving");
    elements.solver.hidden = true;
    elements.welcome.hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function loadLibrary() {
    try {
      const response = await fetch("puzzles.json");
      if (!response.ok) {
        throw new Error(`Could not load puzzle library (${response.status}).`);
      }
      const puzzles = await response.json();
      if (!Array.isArray(puzzles) || !puzzles.length) {
        throw new Error("No published puzzles are available.");
      }

      const fragment = document.createDocumentFragment();
      for (const puzzle of puzzles) {
        const card = document.createElement("button");
        const copy = document.createElement("span");
        card.className = "puzzle-card";
        card.type = "button";
        copy.className = "puzzle-card-copy";

        const title = document.createElement("h2");
        title.textContent = puzzle.title;
        const meta = document.createElement("span");
        meta.className = "puzzle-meta";
        meta.textContent = [puzzle.difficulty, puzzle.size].filter(Boolean).join(" · ");
        const action = document.createElement("span");
        action.className = "puzzle-card-action";
        action.textContent = "Play";
        action.setAttribute("aria-hidden", "true");
        copy.append(title, meta);
        card.append(copy, action);
        card.setAttribute(
          "aria-label",
          ["Play", puzzle.title, meta.textContent].filter(Boolean).join(", "),
        );
        card.addEventListener("click", () => {
          const query = new URLSearchParams({ puzzle: puzzle.slug });
          window.history.replaceState(null, "", `${canonicalHomePath}?${query}`);
          loadPuzzleUrl(puzzle.file);
        });
        fragment.append(card);
      }

      elements.puzzleList.replaceChildren(fragment);
      elements.libraryStatus.textContent = `${puzzles.length} puzzles`;

      const requestedSlug = new URLSearchParams(window.location.search).get("puzzle");
      const requested = puzzles.find((puzzle) => puzzle.slug === requestedSlug);
      if (requested) {
        await loadPuzzleUrl(requested.file);
      }
    } catch (error) {
      elements.libraryStatus.textContent = "Unavailable";
      showToast(
        error instanceof Error
          ? `${error.message} Serve this folder over HTTP to view bundled puzzles.`
          : "Could not load the puzzle library.",
      );
    }
  }

  function handleKeydown(event) {
    if (
      !state ||
      elements.solver.hidden ||
      event.isComposing ||
      event.metaKey ||
      event.ctrlKey ||
      event.altKey
    ) {
      return;
    }

    if (/^[a-zA-Z]$/.test(event.key)) {
      event.preventDefault();
      enterLetter(event.key.toUpperCase());
      return;
    }

    const actions = {
      Backspace: eraseLetter,
      Delete: () => {
        resumeTimerIfNeeded();
        state.values[state.selected] = "";
        state.wrong.delete(state.selected);
        updateGrid();
        saveProgress();
      },
      ArrowLeft: () => moveSpatial(0, -1, "Across"),
      ArrowRight: () => moveSpatial(0, 1, "Across"),
      ArrowUp: () => moveSpatial(-1, 0, "Down"),
      ArrowDown: () => moveSpatial(1, 0, "Down"),
      Enter: switchDirection,
      " ": switchDirection,
      Tab: () => nextEntry(event.shiftKey ? -1 : 1),
    };
    const action = actions[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  }

  function handleTextInput() {
    const letters = elements.keyboardInput.value.toUpperCase().match(/[A-Z]/g) || [];
    elements.keyboardInput.value = "";
    if (!state || elements.solver.hidden) {
      return;
    }
    for (const letter of letters) {
      enterLetter(letter);
    }
  }

  function handleBeforeInput(event) {
    if (!state || elements.solver.hidden) {
      return;
    }
    if (event.inputType.startsWith("delete")) {
      event.preventDefault();
      elements.keyboardInput.value = "";
      eraseLetter();
    } else if (event.inputType === "insertLineBreak") {
      event.preventDefault();
      switchDirection();
    }
  }

  elements.checkButton.addEventListener("click", () => {
    checkPuzzle();
    focusForTyping();
  });
  elements.revealButton.addEventListener("click", () => {
    revealWord();
    focusForTyping();
  });
  elements.resetButton.addEventListener("click", () => {
    resetPuzzle();
    focusForTyping();
  });
  elements.galleryButton.addEventListener("click", showGallery);
  elements.keyboardInput.addEventListener("beforeinput", handleBeforeInput);
  elements.keyboardInput.addEventListener("input", handleTextInput);
  document.addEventListener("keydown", handleKeydown);
  window.addEventListener("beforeunload", saveProgress);

  loadLibrary();
})();
