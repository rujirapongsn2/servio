import asyncio
import websockets
import json
import base64
import audioop
import wave
import math
import struct
import sys
import os

# Constants
WS_URL = "ws://localhost:8000/ws/twilio-stream"
SAMPLE_RATE = 8000
FREQUENCY = 440  # A4 note
DURATION_SEC = 3
CHUNK_SIZE = 160  # Twilio sends 20ms chunks (8000 * 0.02 = 160 samples)

def generate_sine_wave_ulaw(duration_sec=3):
    """Generate a sine wave audio, encoded in u-law."""
    num_samples = duration_sec * SAMPLE_RATE
    audio_data = bytearray()
    
    for i in range(num_samples):
        # Generate sine wave
        sample = 32767 * math.sin(2 * math.pi * FREQUENCY * i / SAMPLE_RATE)
        # Clamp to 16-bit range
        sample = max(-32768, min(32767, int(sample)))
        # Pack to bytes
        pcm_bytes = struct.pack('<h', sample)
        audio_data.extend(pcm_bytes)
    
    # Convert to u-law
    ulaw_data = audioop.lin2ulaw(audio_data, 2)
    return ulaw_data

async def simulate_twilio():
    print(f"Connecting to {WS_URL}...")
    try:
        async with websockets.connect(WS_URL) as ws:
            print("Connected!")

            # 1. Send Start Event
            start_msg = {
                "event": "start",
                "sequenceNumber": "1",
                "start": {
                    "streamSid": "MZ12345",
                    "accountSid": "AC12345",
                    "callSid": "CA12345",
                    "tracks": ["inbound"],
                    "mediaFormat": {
                        "encoding": "audio/x-mulaw",
                        "sampleRate": 8000,
                        "channels": 1
                    }
                },
                "streamSid": "MZ12345"
            }
            await ws.send(json.dumps(start_msg))
            print("Sent 'start' event.")
            
            # 2. Receive potential 'mark' from server (optional) or just start sending
            # Let's send audio
            print("Generating 3 seconds of test audio (sine wave)...")
            ulaw_audio = generate_sine_wave_ulaw(DURATION_SEC)
            
            # Split into chunks of 20ms (160 bytes for u-law)
            print("Sending audio stream...")
            offset = 0
            while offset < len(ulaw_audio):
                chunk = ulaw_audio[offset:offset+CHUNK_SIZE]
                offset += CHUNK_SIZE
                
                payload = base64.b64encode(chunk).decode('utf-8')
                media_msg = {
                    "event": "media",
                    "sequenceNumber": "2",
                    "media": {
                        "track": "inbound",
                        "chunk": "1",
                        "timestamp": "123",
                        "payload": payload
                    },
                    "streamSid": "MZ12345"
                }
                await ws.send(json.dumps(media_msg))
                # Twilio sends approx every 20ms
                await asyncio.sleep(0.02)
            
            print("Finished sending audio. Listening for response...")
            
            # 3. Listen for responses
            received_bytes = 0
            try:
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    if data['event'] == 'media':
                        payload = data['media']['payload']
                        chunk = base64.b64decode(payload)
                        received_bytes += len(chunk)
                        sys.stdout.write(f"\rReceived Response Audio: {received_bytes} bytes")
                        sys.stdout.flush()
                        
                    elif data['event'] == 'mark':
                        print(f"\nReceived Mark: {data['mark']['name']}")
            except websockets.exceptions.ConnectionClosed:
                print("\nConnection closed.")

    except Exception as e:
        print(f"\nError: {e}")
        print("Make sure the server is running on localhost:8000")

if __name__ == "__main__":
    # Check if 'websockets' is installed
    try:
        import websockets
    except ImportError:
        print("Installing websockets library...")
        os.system("uv pip install websockets")
        import websockets

    asyncio.run(simulate_twilio())
