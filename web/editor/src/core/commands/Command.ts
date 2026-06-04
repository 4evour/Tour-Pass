export interface Command {
  type: string;
  description: string;
  execute(): void;
  undo(): void;
}

export class CommandHistory {
  private undoStack: Command[] = [];
  private redoStack: Command[] = [];

  execute(command: Command): void {
    command.execute();
    this.undoStack.push(command);
    this.redoStack = [];
  }

  undo(): Command | null {
    const command = this.undoStack.pop();
    if (command) {
      command.undo();
      this.redoStack.push(command);
    }
    return command ?? null;
  }

  redo(): Command | null {
    const command = this.redoStack.pop();
    if (command) {
      command.execute();
      this.undoStack.push(command);
    }
    return command ?? null;
  }

  canUndo(): boolean {
    return this.undoStack.length > 0;
  }

  canRedo(): boolean {
    return this.redoStack.length > 0;
  }

  getUndoDescription(): string | null {
    return this.undoStack.length > 0
      ? this.undoStack[this.undoStack.length - 1].description
      : null;
  }

  getRedoDescription(): string | null {
    return this.redoStack.length > 0
      ? this.redoStack[this.redoStack.length - 1].description
      : null;
  }

  clear(): void {
    this.undoStack = [];
    this.redoStack = [];
  }
}
