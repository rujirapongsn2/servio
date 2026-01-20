# Agent Monitor (Online Agent) Development Plan

## 1. Overview
The **Online Agent** feature allows Customer Support staff to monitor active chat sessions between users and the AI Agent in real-time. It provides the ability to intervene (take over) the conversation and return control to the AI when necessary.

## 2. Key Features

### 2.1 Dashboard (Active Sessions List)
-   Display a list of all currently active sessions.
-   Show key details for each session:
    -   Session ID / User ID
    -   Start Time
    -   Last Message Time
    -   Current Status (AI Mode / Manual Mode)
    -   Last Message Preview

### 2.2 Real-time Monitoring Interface
-   Clicking a session opens a detailed chat view.
-   **Real-time Updates**: Support staff sees messages from both the User and the AI as they happen (via WebSocket).
-   **Chat History**: Load previous messages in the session.

### 2.3 Control Modes (Takeover/Handover)
-   **Manual Mode (Takeover)**:
    -   Button to pause the AI.
    -   When active, the AI stops processing user input.
    -   Support staff can type and send messages directly to the user.
-   **AI Mode (Handover)**:
    -   Button to resume AI operation.
    -   The AI resumes processing user input and responding automatically.

## 3. Technical Architecture

### 3.1 Backend (FastAPI + WebSockets)
-   **Session Management**:
    -   Maintain a global state of active WebSocket connections.
    -   Store session metadata (mode: `AI` or `MANUAL`).
-   **WebSocket Updates**:
    -   **Admin Connection**: Create a new WebSocket endpoint for admins to subscribe to session updates.
    -   **Broadcasting**: When a user or AI sends a message, broadcast it to the connected admin monitoring that session.
-   **Control Logic**:
    -   Middleware or check in the chat flow: Before AI processes a message, check the session mode.
    -   If `mode == MANUAL`, skip AI generation.
    -   New API endpoints/WebSocket events for Admin to send messages to the User.

### 3.2 Frontend (Next.js)
-   **Admin Route**: `/admin/monitor`
-   **Components**:
    -   `SessionList`: Table/List of active users.
    -   `MonitorChat`: Chat interface for the admin (read-only in AI mode, interactive in Manual mode).
    -   `ControlPanel`: Buttons to toggle `Manual Mode` / `AI Mode`.

## 4. Implementation Steps

### Phase 1: Backend Core & State Management
1.  [ ] Update `ConnectionManager` to track active sessions and their status (AI/Manual).
2.  [ ] Implement WebSocket endpoint for Admins (`/ws/admin/monitor/{session_id}`).
3.  [ ] Implement logic to broadcast user/AI messages to the Admin WebSocket.
4.  [ ] Implement "Intervention" logic:
    -   API to toggle mode (`set_session_mode(session_id, mode)`).
    -   API for Admin to send a message (`admin_send_message(session_id, content)`).
    -   Modify main chat flow to respect `MANUAL` mode (skip LLM call).

### Phase 2: Admin Dashboard (Frontend)
1.  [ ] Create `/admin/monitor` page.
2.  [ ] Implement `ActiveSessionsList` component fetching data from backend.
3.  [ ] Implement real-time updates for the list (new sessions, status changes).

### Phase 3: Monitoring & Control Interface (Frontend)
1.  [ ] Create chat view for Admin.
2.  [ ] Connect to Admin WebSocket to receive real-time messages.
3.  [ ] Implement "Manual Mode" / "AI Mode" toggle buttons.
4.  [ ] Implement message input for Admin (enabled only in Manual Mode).

### Phase 4: Testing & Refinement
1.  [ ] Verify Real-time synchronization.
2.  [ ] Test Takeover flow: User speaks -> Admin sees it -> Admin takes over -> Admin replies -> User sees Admin's reply -> AI stays silent.
3.  [ ] Test Handover flow: Admin switches to AI -> User speaks -> AI replies.
