<img src="./.github/assets/app-icon.png" alt="Voice assistant app icon" width="100" height="100">

# Flutter Agent Starter

This starter app template for [LiveKit Agents](https://docs.livekit.io/agents/overview/) provides a simple voice interface using the [LiveKit Flutter SDK](https://github.com/livekit/client-sdk-flutter). It supports [voice](https://docs.livekit.io/agents/start/voice-ai/), [transcriptions](https://docs.livekit.io/agents/build/text/), [live video input](https://docs.livekit.io/agents/build/vision/#video), and [virtual avatars](https://docs.livekit.io/agents/integrations/avatar/).

This template is compatible with iOS, macOS, Android, and web. It is free for you to use or modify as you see fit.

<img src="./.github/assets/screenshot.png" alt="Voice Assistant Screenshot" height="500">

## Development Modes

### Mode 1: With Local Backend (Full Features)
1. Start your Python/Node.js agent backend on port 5050
2. Run the Flutter app: 
   ```bash
   flutter run
   ```
   *This mode connects to `http://localhost:5050` to fetch tokens.*

### Mode 2: Sandbox Mode (UI Testing Only)
1. Create a `.env` file with:
   ```
   LIVEKIT_SANDBOX_ID=your_sandbox_id_here
   ```
2. Run without backend:
   ```bash
   flutter run --dart-define=LIVEKIT_SANDBOX_ID=your_id
   ```

### Linux Users
If you see GDK-CRITICAL errors, ensure you have:
- GTK 3.0+ installed
- Proper display server (X11/Wayland)
- Run `flutter clean` then `flutter run` after applying fixes.

> [!NOTE]
> To setup without the LiveKit CLI, clone the repository and then either create a `.env` with a `LIVEKIT_SANDBOX_ID`. The app automatically falls back to Sandbox if the local backend is unreachable.

## Feature overview

This starter app supports several features of the agents framework and is intended as a base you can adapt for your own use case.

### Text, video, and voice input

This app supports:

- **Voice**: send microphone audio to your agent. **Requires microphone permissions.**
- **Text**: send text input using the message bar.
- **Video**: optionally share camera and/or screen share tracks to the room so your agent can process visual input (requires an agent/model that supports it).

Related docs:

- Voice agents: https://docs.livekit.io/agents/start/voice-ai/
- Text: https://docs.livekit.io/agents/build/text/
- Vision/video: https://docs.livekit.io/agents/build/vision/#video
- Screen share: https://docs.livekit.io/home/client/tracks/screenshare/

If you have trouble with screen sharing, refer to the docs linked above for more setup instructions.

### Session

The app is built around two core concepts:

- `livekit_client.Session`: connects to LiveKit, dispatches/observes the agent, and provides a message history via `session.messages` as well as helpers like `session.sendText(...)`.
- `livekit_components.RoomContext` / `MediaDeviceContext`: manages local media tracks (microphone, camera, screen share) and their lifecycle.

### Preconnect audio buffer

This app enables `preConnectAudio` by default to capture and buffer audio before the room connection completes. This allows the connection to appear "instant" from the user's perspective and makes the app more responsive.

To disable this feature, set `preConnectAudio` to `false` in `LiveKitService` options (see `lib/core/services/livekit_service.dart`).

### Virtual avatar / agent video

If your agent publishes a video track (for example via a [virtual avatar](https://docs.livekit.io/agents/integrations/avatar/) integration), the app renders the agent's video when available and falls back to an audio visualizer otherwise.

## Token generation in production

In a production environment, you will be responsible for developing a solution to [generate tokens for your users](https://docs.livekit.io/home/server/generating-tokens/) that integrates with your authentication system.

You should replace the logic in `lib/core/services/livekit_service.dart` with your own authentication and token fetching mechanism.

## Running on Simulator / Emulator

To use this template with video (or screen sharing) input, you may need to run the app on a physical device depending on platform and simulator/emulator capabilities. Testing on Simulator/Emulator will still support voice and text modes.

## Contributing

This template is open source and we welcome contributions! Please open a PR or issue through GitHub, and don't forget to join us in the [LiveKit Community Slack](https://livekit.io/join-slack)!
