# VOXA — Voice-Enabled AI Automotive Assistant

VOXA is an intelligent voice assistant designed specifically for automotive manufacturing environments. It provides natural language access to plant data insights through voice and text interfaces, enabling operators and managers to query production metrics, equipment status, and operational data hands-free.

## Features

- **Voice Interaction**: Speech-to-text and text-to-speech capabilities for hands-free operation
- **Natural Language Queries**: Ask questions about production data in plain English
- **Real-time Data Access**: Query live plant data stored in DuckDB
- **Conversational AI**: Powered by Groq's LLM for intelligent responses
- **Web Interface**: Modern React-based dashboard with voice controls
- **Authentication**: Secure user management and session handling
- **Data Visualization**: Interactive charts and metrics display

## Architecture

### Backend (Python/FastAPI)
- **Speech Services**: Whisper for STT, Edge-TTS for TTS
- **AI Engine**: Groq API integration for conversational AI
- **Data Layer**: DuckDB for fast analytical queries on Excel data
- **API Endpoints**: RESTful APIs for chat, speech, queries, and authentication

### Frontend (React/Vite)
- **Voice Controls**: Real-time audio recording and playback
- **Chat Interface**: Message bubbles with markdown support
- **Dashboard**: Production metrics and data visualization
- **Authentication**: Login/signup with protected routes
- **Responsive Design**: Tailwind CSS for modern UI

## Tech Stack

### Backend
- Python 3.8+
- FastAPI
- Whisper (OpenAI)
- Groq API
- DuckDB
- Edge-TTS
- JWT Authentication

### Frontend
- React 19
- Vite
- Tailwind CSS
- Zustand (State Management)
- React Router
- React Hot Toast

## Installation

### Prerequisites
- Python 3.8 or higher
- Node.js 18 or higher
- Git

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```

3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`

4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Configure environment variables:
   Copy `backend/.env.example` to `backend/.env` and fill in your values.

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

## Usage

### Starting the Application

1. Start the backend server:
   ```bash
   cd backend
   python main.py
   ```
   The API will be available at `http://localhost:8000`

2. Start the frontend development server:
   ```bash
   cd frontend
   npm run dev
   ```
   The app will be available at `http://localhost:5173`

### Using the Voice Assistant

1. **Voice Input**: Click the microphone button to start recording
2. **Text Input**: Type your query in the chat input
3. **Ask Questions**: Examples:
   - "What's the current production rate?"
   - "Show me equipment downtime for line A"
   - "How many defects were reported today?"

## API Documentation

Once the backend is running, visit `http://localhost:8000/docs` for interactive API documentation.

## Project Structure

```
VOICE-ASSISTANT/
├── backend/
│   ├── main.py                 # FastAPI application entry point
│   ├── config.py               # Configuration settings
│   ├── requirements.txt        # Python dependencies
│   ├── agents/
│   │   └── automotive_agent.py # AI agent logic
│   ├── routers/
│   │   ├── auth.py            # Authentication endpoints
│   │   ├── chat.py            # Chat/conversation endpoints
│   │   ├── health.py          # Health check endpoints
│   │   ├── history.py         # Conversation history
│   │   ├── query.py           # Data query endpoints
│   │   └── speech.py          # Speech processing endpoints
│   └── services/
│       ├── data_service.py    # Data management (DuckDB)
│       ├── llm_service.py     # LLM integration (Groq)
│       ├── stt_service.py     # Speech-to-text (Whisper)
│       └── tts_service.py     # Text-to-speech (Edge-TTS)
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main React application
│   │   ├── components/        # Reusable UI components
│   │   ├── pages/             # Page components
│   │   ├── services/          # API and utility services
│   │   ├── store/             # Zustand state stores
│   │   └── utils/             # Utility functions
│   ├── package.json           # Node dependencies
│   └── vite.config.js         # Vite configuration
├── data/                      # Data files directory
└── start.bat                  # Windows startup script
```

## Configuration

### Backend Configuration (config.py)
- `HOST`: Server host (default: "0.0.0.0")
- `PORT`: Server port (default: 8000)
- `CORS_ORIGINS`: Allowed CORS origins
- `DATA_DIR`: Path to data directory
- `WHISPER_MODEL`: Whisper model size (default: "base")

### Environment Variables
- `GROQ_API_KEY`: Your Groq API key
- `SECRET_KEY`: JWT secret key for authentication

## Development

### Running Tests
```bash
# Backend tests (if implemented)
cd backend
python -m pytest

# Frontend linting
cd frontend
npm run lint
```

### Building for Production
```bash
# Build frontend
cd frontend
npm run build

# Backend is ready to run with uvicorn
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

See LICENSE file for details.

## Support

For questions or issues, please open an issue on the GitHub repository.