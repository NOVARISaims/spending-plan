// Barcode scanning via the native BarcodeDetector (iOS 17+/Chromium).
// Fully local — no external decoding service. Falls back to manual entry
// (handled by the Scan tab) when the API or camera is unavailable.

const FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'itf'];

export const scannerSupported = () => 'BarcodeDetector' in window;

export class Scanner {
  constructor(video, onCode) {
    this.video = video;
    this.onCode = onCode;
    this.stream = null;
    this.running = false;
  }

  async start() {
    if (!scannerSupported()) throw new Error('no-detector');
    const supported = await window.BarcodeDetector.getSupportedFormats().catch(() => FORMATS);
    this.detector = new window.BarcodeDetector({
      formats: FORMATS.filter((f) => supported.includes(f)),
    });
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    this.video.srcObject = this.stream;
    this.video.setAttribute('playsinline', '');
    await this.video.play();
    this.running = true;
    this._loop();
  }

  async _loop() {
    while (this.running) {
      if (this.video.readyState >= 2) {
        try {
          const codes = await this.detector.detect(this.video);
          if (codes.length && this.running) {
            const value = codes[0].rawValue?.trim();
            if (value) {
              if (navigator.vibrate) navigator.vibrate(60);
              this.running = false;
              this.onCode(value);
              break;
            }
          }
        } catch { /* transient detector errors: keep scanning */ }
      }
      await new Promise((r) => setTimeout(r, 180));
    }
  }

  stop() {
    this.running = false;
    if (this.stream) {
      for (const track of this.stream.getTracks()) track.stop();
      this.stream = null;
    }
    this.video.srcObject = null;
  }
}
