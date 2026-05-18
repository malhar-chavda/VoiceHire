class PCMProcessor extends AudioWorkletProcessor {
  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0];
      
      // Calculate peak amplitude for noise gating
      let peak = 0;
      for (let i = 0; i < channelData.length; i++) {
        const abs = Math.abs(channelData[i]);
        if (abs > peak) peak = abs;
      }

      const i16 = new Int16Array(channelData.length);
      
      // If below threshold, send silence (zeros) to prevent false interruptions
      if (peak < 0.015) {
        // i16 is already initialized to zeros
      } else {
        // Convert Float32 to Int16
        for (let i = 0; i < channelData.length; i++) {
          const s = Math.max(-1, Math.min(1, channelData[i]));
          i16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
      }
      
      this.port.postMessage(i16.buffer, [i16.buffer]);
    }
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
