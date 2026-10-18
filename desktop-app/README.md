# AI Optical Design Engineer - Desktop App

Electron wrapper for easy one-click launch of the optical design software.

## Features

- ✅ One-click launch - no terminal needed
- ✅ Bundled Python backend
- ✅ System tray integration
- ✅ Native window with menu bar
- ✅ Auto-start backend with health check
- ✅ Error handling with user-friendly messages
- ✅ Cross-platform: Windows, Mac, Linux

## Installation

### Pre-built Binaries

Download from the [Releases](https://github.com/USERNAME/ai-optical-design-engineer/releases) page:

- **Windows**: `AI-Optical-Design-Engineer-Setup-x.x.x.exe`
- **Mac**: `AI-Optical-Design-Engineer-x.x.x.dmg`
- **Linux**: `AI-Optical-Design-Engineer-x.x.x.AppImage`

### Build from Source

```bash
# Install dependencies
cd desktop-app
npm install

# Build frontend
cd ../frontend
npm run build

# Build desktop app
cd ../desktop-app
npm run build        # Build for current platform
npm run build:win    # Windows
npm run build:mac    # Mac
npm run build:linux  # Linux
```

Output will be in `desktop-app/dist-electron/`.

## Development

```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
uvicorn api.main:app --reload

# Terminal 2: Frontend  
cd frontend
npm run dev

# Terminal 3: Electron
desktop-app
npm start
```

## Architecture

```
desktop-app/
├── electron/
│   ├── main.js          # Electron main process
│   └── preload.js       # Preload script for IPC
├── src/
│   └── index.html       # Loading screen
├── assets/              # Icons and resources
└── package.json         # Build configuration
```

## Building Installers

### Windows (NSIS)
```bash
npm run build:win
```

Creates:
- `AI-Optical-Design-Engineer-Setup-x.x.x.exe` (installer)
- `AI-Optical-Design-Engineer-x.x.x-portable.exe` (portable)

### Mac (DMG)
```bash
npm run build:mac
```

Creates:
- `AI-Optical-Design-Engineer-x.x.x.dmg`

### Linux (AppImage)
```bash
npm run build:linux
```

Creates:
- `AI-Optical-Design-Engineer-x.x.x.AppImage`

## License

MIT
