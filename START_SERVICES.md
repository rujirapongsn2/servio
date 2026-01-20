# วิธีเริ่ม Services ทั้งหมด

## Option 1: รันด้วย Docker (แนะนำสำหรับ Production)

```bash
# Start ทุก services (Frontend, Backend, Database, Nginx)
cd /Users/rujirapongair/myapp/servio
docker-compose up -d

# ดู logs
docker-compose logs -f

# เข้าถึงที่
http://localhost  # หรือ http://your-domain.com
```

## Option 2: รัน Development แยกกัน (สำหรับพัฒนา)

### 1. Start Database (ต้องมี Docker)

```bash
cd /Users/rujirapongair/myapp/servio
docker-compose up -d postgres
```

### 2. Start Backend Server

```bash
cd /Users/rujirapongair/myapp/servio/server
source .venv/bin/activate
python server.py
```

Backend จะรันที่: `http://localhost:8000`

### 3. Start Frontend Server (แยก terminal)

```bash
cd /Users/rujirapongair/myapp/servio/frontend
npm run dev
```

Frontend จะรันที่: `http://localhost:3000`

## ตรวจสอบว่า Services รันอยู่

```bash
# เช็ค Docker containers
docker ps

# เช็ค ports
lsof -i :3000  # Frontend
lsof -i :8000  # Backend
lsof -i :5432  # PostgreSQL
```

## Troubleshooting

### Frontend ไม่แสดง API Key Manager

1. เช็คว่า login แล้วหรือยัง
2. เปิด Browser Console (F12) ดู errors
3. ลอง logout แล้ว login ใหม่

### Backend Error: Could not connect to postgres

```bash
# Start postgres ด้วย Docker
cd /Users/rujirapongair/myapp/servio
docker-compose up -d postgres

# หรือแก้ .env ให้ใช้ localhost
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/voice_agents
```

### Port ถูกใช้อยู่แล้ว

```bash
# Kill process ที่ใช้ port 3000
lsof -ti:3000 | xargs kill -9

# Kill process ที่ใช้ port 8000
lsof -ti:8000 | xargs kill -9
```

## วิธีเข้าใช้งาน

### Admin Panel (ต้อง login)
- URL: `http://localhost:3000/admin/login`
- Username: `admin`
- Password: (ดูใน backend config)

### Widget Generator
- URL: `http://localhost:3000/admin/tools/widget`
- ต้อง login ก่อน!

### Test Widget
- URL: `http://localhost:3000/widget?apiKey=sk_xxxxx`

## Quick Start (รวมทุกอย่าง)

```bash
# Terminal 1: Start Database
docker-compose up -d postgres

# Terminal 2: Start Backend
cd server && source .venv/bin/activate && python server.py

# Terminal 3: Start Frontend
cd frontend && npm run dev

# จากนั้นเปิด browser:
# 1. http://localhost:3000/admin/login (Login ก่อน)
# 2. http://localhost:3000/admin/tools/widget (สร้าง API Key)
```
