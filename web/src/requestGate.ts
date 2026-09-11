export class RequestGate {
  private generation = 0;
  private controller: AbortController | null = null;

  begin() {
    this.controller?.abort();
    this.controller = new AbortController();
    return { generation: ++this.generation, signal: this.controller.signal };
  }

  isCurrent(generation: number) { return generation === this.generation; }
  abort() { this.controller?.abort(); }
}
