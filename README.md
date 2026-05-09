# Servio - ระบบผู้ช่วยบริการลูกค้า (Customer Support Agent)

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![FastAPI](https://img.shields.io/badge/Built_with-FastAPI-yellow)
![NextJS](https://img.shields.io/badge/Built_with-NextJS-blue)
![OpenAI API](https://img.shields.io/badge/Powered_by-OpenAI_API-orange)

Servio คือระบบผู้ช่วยบริการลูกค้าที่รองรับการสั่งงานด้วยเสียงอันทรงพลัง สร้างขึ้นด้วย [Agents SDK](https://openai.github.io/openai-agents-python) ของ OpenAI และ Python ส่วน Backend ใช้ FastAPI ที่รองรับ WebSocket ในขณะที่ Frontend สร้างด้วย Next.js เพื่อมอบประสบการณ์การใช้งานที่ลื่นไหลทั้งในรูปแบบเสียงและข้อความ

## คุณสมบัติหลัก

- **ระบบสั่งงานด้วยเสียงและแชท** - รองรับทั้งการสนทนาด้วยเสียง (Push-to-talk) และการพิมพ์ข้อความ
- **ระบบ Multi-Agent** - มี AI Agent เฉพาะทางหลายตัวที่ทำงานร่วมกันและส่งต่อการสนทนาได้อย่างราบรื่น
- **Admin Dashboard** - แผงควบคุมสำหรับผู้ดูแลระบบเพื่อจัดการ Agent เครื่องมือ และการตั้งค่าต่างๆ ครบจบในที่เดียว
- **Widget Embedding** - โค้ด Widget สำหรับนำไปติดหน้าเว็บไซต์ได้ง่าย รองรับทั้ง Chat และ Voice
- **Custom Tools Integration** - รองรับการเชื่อมต่อกับ API ภายนอก, MCP tools และ Gemini File Search
- **Dynamic Agent Configuration** - สร้างและตั้งค่า Agent ผ่านหน้า Admin ได้ทันทีโดยไม่ต้องแก้โค้ด
- **Real-time Monitoring** - ติดตามสถานะเซสชันและการทำงานของ Agent ได้แบบเรียลไทม์
- **Multi-turn Conversations** - รองรับการสนทนาโต้ตอบต่อเนื่อง โดยระบบจะจำบริบทก่อนหน้าได้
- **Streaming Responses** - แสดงผลข้อความและเสียงแบบ Streaming เพื่อการตอบสนองที่รวดเร็ว
- **Softnix Integration** - มีระบบเชื่อมต่อกับ Softnix GenAI knowledge base ในตัว

Servio ถูกออกแบบมาให้เป็นโซลูชัน Customer Support ที่พร้อมใช้งานในระดับ Production (Production-Ready) และสามารถปรับแต่งหรือต่อยอดให้เข้ากับความต้องการของธุรกิจคุณได้

## สารบัญ

- [คุณสมบัติหลัก](#คุณสมบัติหลัก)
- [สถาปัตยกรรม Multi-Agent](#สถาปัตยกรรม-multi-agent)
- [File Store Agents](#file-store-agents)
- [การนำ Widget ไปใช้งาน](#การนำ-widget-ไปใช้งาน)
- [ความต้องการของระบบ](#ความต้องการของระบบ)
- [เริ่มต้นใช้งาน](#เริ่มต้นใช้งาน)
  - [การใช้งานผ่าน Docker (แนะนำ)](#การใช้งานผ่าน-docker-แนะนำ-)
  - [การติดตั้งแบบ Manual (สำหรับนักพัฒนา)](#การติดตั้งแบบ-manual-สำหรับนักพัฒนา)
- [การ Deploy ด้วย Docker](#การ-deploy-ด้วย-docker)
  - [คู่มือ Production Deployment](#คู่มือ-production-deployment)
- [การใช้งาน Admin & Agents](#การใช้งาน-admin--agents)
- [Screenshots & GIFs](#screenshots--gifs)
- [Contributing](#contributing)
- [License](#license)

## สถาปัตยกรรม Multi-Agent

ตัวอย่างแอปพลิเคชันนี้รองรับ **Multi-Agent** โดยมี **Coordinator Agent** เป็นค่าตั้งต้นเพียงตัวเดียว (built-in) ทำหน้าที่เปิดบทสนทนาและตอบเองได้ทันที เมื่อคุณสร้าง Agent เพิ่มในฐานข้อมูล Coordinator จะดึงขึ้นมาเป็น handoffs ให้อัตโนมัติ

### โครงสร้าง Agent ปัจจุบัน

#### **Coordinator Agent** (ตัวประสานงานหลัก) 🎯
- **บทบาท**: จุดเริ่มทุกการสนทนา ทักทาย รับเรื่อง และโอนต่อให้ผู้เชี่ยวชาญจากฐานข้อมูลถ้ามี
- **คำสั่ง**: "คุณเป็นผู้ประสานงาน จัดการคำถามเองก่อน และถ้ามี Agent เฉพาะทางในระบบ ให้โอนต่อให้เหมาะสม"
- **เครื่องมือพื้นฐาน**: ไม่มี (ตอบเองด้วยโมเดล)
- **handoffs**: จะถูกเติมด้วย Agent ที่สร้างใน Admin (เช่น Sales, Support, IT, Dtwin ฯลฯ)

### ตัวอย่างการเพิ่ม Agent ในฐานข้อมูล
- สร้าง "Softnix Sales Agent" พร้อม tool `get_softnix_info` → Coordinator โอนให้เมื่อลูกค้าถามเรื่องสินค้า
- สร้าง "Support Agent" พร้อมเครื่องมือสั่งซื้อ/คืนเงิน → Coordinator โอนให้เมื่อพูดถึงคำสั่งซื้อ
- สร้าง "IT Agent" → Coordinator โอนให้เมื่อถามเรื่องปัญหาระบบ

### การทำงานของระบบส่งต่อ Agent (Handoffs)

เมื่อ Coordinator ตัดสินใจโอนสาย จะเห็นข้อความ "**Transferred to [Agent Name]**" ในการสนทนา ซึ่งหมายถึงเปลี่ยนผู้ตอบเป็น Agent ปลายทาง

**ขั้นตอนทางเทคนิค**:
1. Agent ปัจจุบัน (เริ่มจาก Coordinator) ตัดสินใจโอนสาย → `output.last_agent` เปลี่ยนค่า
2. Backend อัปเดต `self.latest_agent = output.last_agent`
3. WebSocket ส่งข้อความแจ้งชื่อ `agent_name` ใหม่
4. Frontend แสดงข้อความ "Transferred to [Agent Name]"
5. Coordinator จะรวม Agent จาก Database เป็นปลายทางให้อัตโนมัติ (เช่น Dtwin, Sales, Support)

### แผนผังการทำงาน (Flow Diagram)

```
                    ┌─────────────────────┐
                    │  เริ่มการสนทนา        │
                    │ (Coordinator Agent) │
                    └──────────┬──────────┘
                               │
                        ลูกค้าพูดว่าอะไร?
                               │
        ┌───────────────┬─────────────┬───────────────┐
        ▼               ▼             ▼
┌───────────────┐  ┌──────────────┐  ┌───────────────┐
│ Sales Agent   │  │ Support Agent│  │   Dtwin Agent │
│   (จาก DB)    │  │    (จาก DB)  │  │     (จาก DB) │
└───────────────┘  └──────────────┘  └───────────────┘

เส้นทาง:
• คำถาม Softnix → Softnix Sales Agent
• คำแนะนำแฟชั่น → Stylist Agent
• ปัญหาคำสั่งซื้อ/คืนเงิน → Customer Support Agent
• คำถาม DTWIN → Dtwin Agent (จาก Database)
• Agent อื่นๆ ใน DB จะปรากฏเป็นเส้นทางเพิ่มเติมตามที่ตั้งค่าใน Admin
```

### ทำไมต้อง Multi-Agent?

✅ **ความเชี่ยวชาญเฉพาะด้าน** - แต่ละ Agent เก่งในเรื่องของตัวเอง
✅ **คำตอบแม่นยำขึ้น** - ใช้เครื่องมือที่ตรงจุด
✅ **การส่งต่อที่ยืดหยุ่น** - ส่งงานต่อตามบริบทการคุย
✅ **ขยายงานง่าย** - เพิ่ม Agent ใหม่ได้ตลอดเวลา

### การปรับแต่ง Agent

แก้ไขไฟล์ `server/app/agent_config.py` เพื่อ:
- เพิ่ม Agent ใหม่พร้อมเครื่องมือพิเศษ
- แก้ไขคำสั่งและพฤติกรรมของ Agent
- ตั้งค่าความสัมพันธ์การส่งต่องาน
- เพิ่ม Custom Function Tools

## การนำ Widget ไปใช้งาน

Servio มี Widget ที่คุณสามารถนำไปแปะหน้าเว็บไซต์ได้ทันที เพื่อให้ลูกค้าเข้าถึง AI Agent ของคุณได้ง่ายๆ

### วิธีติดตั้งด่วน (Quick Start)

1. **สร้างโค้ด Widget**: ไปที่ Admin Console → Tools → Widget
2. **ตั้งค่า Widget**:
   - เลือกประเภท: `voice` (พร้อมปุ่ม Push-to-talk) หรือ `chat` (พิมพ์คุยอย่างเดียว)
   - เลือกตำแหน่ง: ขวาล่าง (`bottom-right`) หรือ ซ้ายล่าง (`bottom-left`)
   - ตั้งค่า Server URL (ค่าเริ่มต้น: `https://localhost`)
3. **คัดลอกและนำไปใช้**: นำโค้ดที่ได้ไปวางใน HTML ของเว็บไซต์คุณ

### ตัวอย่างโค้ด Widget

```html
<!-- Servio Chat Widget -->
<script
  src="https://localhost/embed.js"
  data-type="chat"
  data-position="bottom-right"
  data-server-url="https://localhost">
</script>
```

### ประเภทของ Widget

**Chat Widget** (`data-type="chat"`):
- อินเทอร์เฟซแบบแชทข้อความ
- ไม่ต้องขอสิทธิ์ไมโครโฟน
- เหมาะสำหรับผู้ใช้ Desktop หรือสถานการณ์ที่ไม่สะดวกใช้เสียง

**Voice Widget** (`data-type="voice"`):
- คุยด้วยเสียงแบบ Push-to-talk
- จะขอสิทธิ์เข้าถึงไมโครโฟน
- เหมาะสำหรับการใช้งานแบบ Hands-free

### การปรับแต่ง

ตัว Widget จะทำสิ่งเหล่านี้ให้อัตโนมัติ:
- ปรับ Branding ตาม Agent (แสดงชื่อและโลโก้)
- เข้ากับธีมของคุณ (รองรับ Light/Dark mode)
- ตอบสนองต่อการสัมผัสด้วย Visual Feedback
- แสดงประวัติการสนทนาพร้อมจัดรูปแบบสวยงาม
- จัดการเรื่องการส่งต่อ Agent ให้เนียนไปกับการคุย

## File Store Agents

แอปฯ นี้มาพร้อมระบบ **File Store Agent** ที่ช่วยให้คุณสร้าง Agent ค้นหาเอกสารได้ โดยใช้พลังของ Google Gemini File Search API ทำให้ AI ตอบคำถามจากเอกสารที่คุณอัปโหลดได้

### File Store Agents คืออะไร?

คือ Agent พิเศษที่สามารถค้นหาและดึงข้อมูลจากชุดเอกสารที่คุณอัปโหลด โดยใช้ความสามารถ RAG (Retrieval-Augmented Generation) ของ Gemini เพื่อให้คำตอบที่ถูกต้องพร้อมอ้างอิงแหล่งที่มา

### คุณสมบัติเด่น

✅ **Multi-File Upload** - อัปโหลดทีละหลายไฟล์ได้ (PDF, TXT, MD, DOC, DOCX)
✅ **Drag-and-Drop Interface** - ลากไฟล์มาวางเพื่ออัปโหลดได้ง่ายๆ
✅ **Auto-Tool Creation** - สร้างเครื่องมือค้นหาให้อัตโนมัติทันทีที่สร้าง File Store
✅ **File Management** - เพิ่มหรือลบไฟล์ได้ตลอดเวลา
✅ **Detailed Testing** - ทดสอบการค้นหาพร้อมดูแหล่งอ้างอิงและ Metadata
✅ **Thai Filename Support** - รองรับชื่อไฟล์ภาษาไทยอัตโนมัติ
✅ **Progress Tracking** - มีแถบแสดงความคืบหน้าขณะอัปโหลด

### วิธีสร้าง File Store Agent

1. **ไปที่ Admin Console**
   - เข้าไปที่ `http://localhost:3001/admin` (หรือพอร์ตที่คุณตั้งไว้)
   - คลิกเมนู "Agents" ด้านข้าง
   - เลือกแท็บ "File Store Agents"

2. **สร้าง File Store ใหม่**
   - คลิกปุ่ม "New File Store"
   - ตั้งชื่อที่สื่อความหมาย (เช่น "Product Documentation")
   - อัปโหลดเอกสาร (รองรับหลายไฟล์)
   - ติ๊กถูก "Create Tool Automatically" (ค่าเริ่มต้น: เปิด)
   - คลิก "Create File Store"

3. **Tool จะถูกสร้างให้อัตโนมัติ**
   - ชื่อ Tool: `{store_name}_search`
   - Tool นี้จะพร้อมให้ทุก Agent ในระบบเลือกใช้ได้
   - Agent จะใช้ Tool นี้ค้นหาข้อมูลในเอกสารชุดนั้น

4. **ทดสอบ File Store ของคุณ**
   - คลิกปุ่มสีเขียว "Play" ข้างๆ File Store
   - พิมพ์คำถามเกี่ยวกับเอกสาร
   - ดูคำตอบของ AI ซึ่งจะประกอบด้วย:
     - คำตอบจากเนื้อหาในเอกสาร
     - แหล่งอ้างอิง (Grounding sources) ว่าเอามาจากไฟล์ไหน
     - เวลาที่ใช้ตอบและ Metadata

5. **จัดการไฟล์**
   - คลิกปุ่มสีฟ้า "Upload" เพื่อจัดการไฟล์
   - ดูรายชื่อไฟล์ทั้งหมด
   - อัปโหลดเพิ่ม หรือลบไฟล์บางตัวออก

### ตัวอย่างการใช้งาน (Use Cases)

**Product Documentation** (คู่มือสินค้า)
```
Store: "Product Manuals"
Files: product_guide.pdf, faq.pdf, specifications.pdf
Use case: ให้ Customer support agent ตอบคำถามเชิงเทคนิค
```

**HR Knowledge Base** (ฝ่ายบุคคล)
```
Store: "HR Policies"
Files: employee_handbook.pdf, leave_policy.pdf, benefits.pdf
Use case: ให้ HR Chatbot ตอบคำถามเรื่องสวัสดิการพนักงาน
```

**Legal Documents** (กฎหมาย)
```
Store: "Legal Contracts"
Files: contract_template.pdf, terms.pdf, privacy_policy.pdf
Use case: ให้ผู้ช่วยกฎหมายช่วยดูเงื่อนไขในสัญญา
```

### การนำ Tool ไปใช้กับ Agent

เมื่อสร้าง File Store แบบเปิด auto-tool แล้ว คุณสามารถนำ Tool ไปใส่ให้ Agent ตัวไหนก็ได้:

1. ไปที่แท็บ "Agents" ใน Admin
2. สร้างหรือแก้ไข Agent
3. ในส่วน "Tools" ให้เลือก Tool ที่ถูกสร้างขึ้น (เช่น "product_docs_search")
4. กด Save Agent

เพียงเท่านี้ เมื่อผู้ใช้คุยกับ Agent ตัวนั้น มันก็จะสามารถค้นหาเอกสารของคุณเพื่อมาตอบคำถามได้!

### การตั้งค่า API

การใช้ File Store Agents จำเป็นต้องมี Gemini API key:

1. ขอ API key ที่: https://ai.google.dev/
2. ใส่ในไฟล์ `.env`:
   ```bash
   GEMINI_API_KEY=your_api_key_here
   ```

### รายละเอียดทางเทคนิค

- **Backend**: `server/app/gemini_service.py` จัดการการเชื่อมต่อ Gemini API ทั้งหมด
- **Database**: เก็บ Metadata ของ File Store และรายการไฟล์ใน PostgreSQL
- **File Upload**: รองรับไฟล์ได้สูงสุด 10MB ต่อไฟล์ (ตั้งค่าเพิ่มได้)
- **Supported Formats**: PDF, TXT, MD, DOC, DOCX
- **Unicode Support**: ระบบจัดการชื่อไฟล์ที่ไม่ใช่ภาษาอังกฤษให้อัตโนมัติ

### การแก้ไขปัญหาเบื้องต้น (Troubleshooting)

**ปัญหา**: อัปโหลดไฟล์ชื่อไทยไม่ได้
- **วิธีแก้**: ระบบจัดการให้แล้วโดยอัตโนมัติ (เปลี่ยนชื่อไฟล์ชั่วคราวเป็น ASCII เพื่ออัปโหลด)

**ปัญหา**: ค้นหาแล้วไม่เจอผลลัพธ์
- **วิธีแก้**: ตรวจสอบว่าเอกสารมีเนื้อหาที่เกี่ยวข้อง และลองเปลี่ยนคำถามดู

**ปัญหา**: อัปโหลดช้า
- **วิธีแก้**: ไฟล์ใหญ่อาจใช้เวลาประมวลผลนาน ให้ดูความคืบหน้าที่ Progress bar

## ความต้องการของระบบ

- **OpenAI API Key**: จำเป็นสำหรับการทำงานของ AI และ Voice Processing
- **Gemini API Key** (Optional): สำหรับใช้ฟีเจอร์ File Store Agents
- **Docker**: (แนะนำ) สำหรับการรันระบบโดยไม่ต้องลงโปรแกรมอื่นเพิ่ม
- **Node.js และ Python**: (กรณีรันแบบ Manual)
- **uv**: (Package manager ของ Python)

## เริ่มต้นใช้งาน

### การใช้งานผ่าน Docker (แนะนำ) 🐳

วิธีที่ง่ายที่สุดคือใช้ Docker ไม่ต้องลง Node.js, Python หรือ uv เอง!

1. **สิ่งที่ต้องมี:**
   - ติดตั้ง [Docker Desktop](https://docs.docker.com/get-docker/)
   - ตรวจสอบว่า Docker รันอยู่

2. **ตั้งค่า API keys:**

   คัดลอกไฟล์ตัวอย่าง `.env.example` (มีค่าเริ่มต้นสำหรับ backend/frontend แล้ว) แล้วเติมค่าให้ครบ:

   ```bash
   cp .env.example .env
   # ใน .env ให้ใส่อย่างน้อย:
   # - OPENAI_API_KEY=...             (จำเป็น)
   # - JWT_SECRET_KEY=...             (ตั้งค่าใหม่สำหรับ production)
   # - SOFTNIX_API_KEY / GEMINI_API_KEY (ถ้ามี)
   # - NEXT_PUBLIC_API_URL / NEXT_PUBLIC_WEBSOCKET_ENDPOINT (แก้เป็นโดเมนจริงเวลา deploy)
   ```

3. **Clone Repository:**

   ```bash
   git clone https://github.com/rujirapongsn2/servio.git
   cd servio/
   ```

4. **รันด้วย Docker:**

   ```bash
   # Start Servio stack
   ./services.sh start
   ```

   คำสั่ง service manager:
   ```bash
   ./services.sh start frontend
   ./services.sh restart backend
   ./services.sh rebuild frontend
   ./services.sh stop
   ./services.sh status
   ./services.sh logs backend
   ./services.sh update
   ```

   `./start.sh` ยังใช้งานได้เป็น compatibility wrapper แต่แนะนำให้ใช้ `./services.sh` เป็นหลัก

5. **แก้ไขปัญหา SSL Certificate Permissions (ถ้าจำเป็น):**

   หากพบปัญหา Nginx ไม่สามารถอ่านไฟล์ SSL certificates ได้ (Permission denied) ให้รันสคริปต์แก้ไข:

   ```bash
   # แก้ไข permissions ของ SSL certificates
   ./fix_certs_permissions.sh

   # หลังจากนั้นรีสตาร์ท Nginx
   docker compose restart nginx
   ```

   สคริปต์นี้จะ:
   - ตรวจสอบว่ามีไฟล์ `nginx/certs/server.crt` และ `server.key` อยู่หรือไม่
   - เปลี่ยน permissions เป็น 644 เพื่อให้ Nginx container อ่านได้
   - แสดงผลลัพธ์การดำเนินการ

   **ช่องทางเข้าใช้งาน:**
   - Frontend: [`https://localhost`](https://localhost)
   - Admin Console: [`https://localhost/admin`](https://localhost/admin)
   - Backend API: [`https://localhost/api`](https://localhost/api)
   - WebSocket: `wss://localhost/ws`

   **คำสั่ง Docker Direct** (ถ้าคุณถนัดแบบพิมพ์เอง):
   ```bash
   # Build และ Start services
   docker compose up -d

   # ดู Logs
   docker compose logs -f

   # Stop services
   docker compose down
   ```

### การติดตั้งแบบ Manual (Development)

ถ้าไม่อยากใช้ Docker:

1. **ตั้งค่า API keys:**

   คัดลอก `.env.example` แล้วใส่ค่าที่จำเป็น:

   ```bash
   cp .env.example .env
   # Required
   # OPENAI_API_KEY=<your_openai_api_key>
   # JWT_SECRET_KEY=<generate_a_secure_value>
   # Frontend endpoints (ปรับเป็นโดเมนจริงเวลา deploy)
   # NEXT_PUBLIC_API_URL=http://localhost:8000
   # NEXT_PUBLIC_WEBSOCKET_ENDPOINT=ws://localhost:8000/ws
   # Optional integrations: SOFTNIX_API_KEY / GEMINI_API_KEY
   ```

   หรือจะตั้งค่า `OPENAI_API_KEY` เป็น environment variable ในเครื่องเลยก็ได้

2. **Clone Repository:**

   ```bash
   git clone https://github.com/rujirapongsn2/servio.git
   cd servio/
   ```

3. **ติดตั้ง Dependencies:**

   ต้องลง dependency ทั้งฝั่ง frontend และ server รันคำสั่งนี้ที่ root:

   ```bash
   make sync
   ```

4. **รันแอปพลิเคชัน:**

   มีหลายทางเลือก:

   **ทางเลือก 1: ใช้ Make (Production Mode)**
   ```bash
   make serve
   ```
   รันแอปในโหมด Production ที่ [`http://localhost:3000`](http://localhost:3000)

   **ทางเลือก 2: Development Mode with Hot Reload**
   ```bash
   cd frontend && npm run dev
   ```
   - Frontend: [`http://localhost:3001`](http://localhost:3001) (หรือพอร์ตอื่นถ้าไม่ว่าง)
   - Backend: [`http://localhost:8000`](http://localhost:8000)
   - WebSocket: `ws://localhost:8000/ws`

   **ทางเลือก 3: รันแยกกัน**
   ```bash
   # Terminal 1 - Frontend only
   cd frontend && npm run dev:next

   # Terminal 2 - Backend only
   cd server && uv run server.py
   ```

   **พอร์ตที่ใช้งาน:**
   - Frontend: `3000` (production) หรือ `3001+` (dev)
   - Backend: `8000`
   - Admin Console: [`http://localhost:3001/admin`](http://localhost:3001/admin)

## การ Deploy ด้วย Docker

Servio มาพร้อมชุด Docker deployment ที่พร้อมสำหรับ Production และใช้สถาปัตยกรรมแบบ Multi-container

### สถาปัตยกรรม (Architecture)

Docker setup ใช้ **docker compose** จัดการ 4 services หลัก:

- **Backend Container** (Python 3.11 + FastAPI + uvicorn)
  - Port: 8000
  - ติดตั้ง dependency อัตโนมัติด้วย `uv`
  - เชื่อมต่อ PostgreSQL database ผ่าน Environment Variables
  - มี Health checks ที่ endpoint `/api/admin/sessions`

- **Frontend Container** (Node.js 20 + Next.js)
  - Port: 3000
  - Multi-stage build เพื่อขนาด image ที่เล็ก
  - รันด้วย non-root user เพื่อความปลอดภัย
  - Health checks ที่ HTTP root endpoint

- **Nginx Container** (Reverse proxy)
  - เปิด Port 80/443
  - Route ไปยัง frontend/backend และ WebSocket

- **PostgreSQL Container** (PostgreSQL 15)
  - เก็บข้อมูลใน Docker volume `postgres_data`

- **Shared Networks** (`proxy-network`, `db-network`)
  - ให้ service ภายในคุยกันได้อย่างแยกขอบเขต
  - Internal DNS resolution (เรียกหากันด้วยชื่อ service ได้เลย)

### โครงสร้างไฟล์ Docker

```
servio/
├── docker-compose.yml          # Service orchestration
├── services.sh                 # CLI service manager
├── start.sh                    # Compatibility wrapper
├── .env                        # Environment variables (create from .env.example)
├── .env.example                # Template for environment variables
├── server/
│   ├── Dockerfile            # Backend container definition
│   ├── .dockerignore        # Exclude unnecessary files
│   └── data/                # Data volume
└── frontend/
    ├── Dockerfile           # Frontend container definition (multi-stage)
    └── .dockerignore       # Exclude node_modules, .next, etc.
```

### Environment Variables

คัดลอกไฟล์ตัวอย่างแล้วแก้ไขค่า:

```bash
cp .env.example .env
```

ตัวแปรหลักใน `.env`:

```bash
# Required
OPENAI_API_KEY=your_openai_api_key
JWT_SECRET_KEY=change_me_in_production

# Frontend / public endpoints
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WEBSOCKET_ENDPOINT=ws://localhost:8000/ws

# Optional integrations
SOFTNIX_API_KEY=your_softnix_api_key    # Optional
GEMINI_API_KEY=your_gemini_api_key      # Optional
SOFTNIX_API_INPUTS=product_id,customer_id

# Docker Configuration (optional, defaults provided)
BACKEND_PORT=8000
FRONTEND_PORT=3000
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/voice_agents
TOOL_TIMEOUT_SECONDS=60
SQL_ECHO=false

# Production CORS (ระบุโดเมนด้วยจุลภาค)
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### Database Persistence

- **PostgreSQL**: ข้อมูลหลักทั้งหมดจะถูกเก็บใน PostgreSQL service ที่กำหนดใน docker-compose หรือ external DB

### การใช้สคริปต์จัดการ Services

Servio ใช้ `./services.sh` เป็นคำสั่งหลักสำหรับจัดการ Docker services:

```bash
./services.sh <command> [service] [options]
```

**Commands:**
- `./services.sh start` - start ทั้ง stack
- `./services.sh start frontend` - start frontend พร้อม dependencies ที่จำเป็น
- `./services.sh restart backend` - restart เฉพาะ backend
- `./services.sh rebuild frontend` - rebuild image แล้ว recreate frontend
- `./services.sh stop` - stop ทั้ง stack โดยไม่ลบ volume/database
- `./services.sh status` - ดูสถานะ containers
- `./services.sh logs backend` - tail logs ของ backend
- `./services.sh update` - `git pull --ff-only`, rebuild และ recreate services

**Services:** `all`, `frontend`, `backend`, `postgres`/`db`, `nginx`/`proxy`

**Options:** `--no-cache`, `--foreground`, `--kill-ports`, `--allow-dirty`

### คู่มือ Production Deployment

ส่วนนี้แนะนำการ Deploy บน Production Server พร้อม SSL/HTTPS

#### สิ่งที่ต้องเตรียม (Prerequisites)
- Server ที่มี Domain name (เช่น `yourdomain.com`)
- DNS records ชี้มาที่ IP Server ของคุณ
- Firewall เปิดพอร์ต 80 และ 443

#### ขั้นตอนที่ 1: ตั้งค่า Environment Variables

สร้างหรืออัปเดตไฟล์ `.env` สำหรับ Production:

```bash
# API Keys (จำเป็น)
OPENAI_API_KEY=your_openai_api_key
SOFTNIX_API_KEY=your_softnix_api_key  # Optional
GEMINI_API_KEY=your_gemini_api_key    # Optional

# ตั้งค่า Database (PostgreSQL)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=voice_agents
POSTGRES_PORT=5432
DATABASE_URL=postgresql://postgres:your_secure_password_here@postgres:5432/voice_agents

# Server Ports
BACKEND_PORT=8000
FRONTEND_PORT=3000

# Production Environment
ENVIRONMENT=production

# ⚠️ สำคัญมาก: Production WebSocket URL
# สำหรับ HTTPS Deployment ต้องใช้ wss:// (secure WebSocket)
# แทนที่ yourdomain.com ด้วยโดเมนจริงของคุณ
NEXT_PUBLIC_WEBSOCKET_ENDPOINT=wss://yourdomain.com/ws

# CORS Origins (คั่นด้วย comma)
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

**หมายเหตุสำคัญ:**
- `NEXT_PUBLIC_WEBSOCKET_ENDPOINT` ต้องเป็น `wss://` (ไม่ใช่ `ws://`) สำหรับเว็บ HTTPS
- ตัวแปรนี้จะถูกฝังลงไปตอน Build frontend - **ต้อง Rebuild ใหม่** ทุกครั้งที่เปลี่ยนค่า
- Browser ปัจจุบันบังคับให้ใช้ HTTPS เท่านั้นถึงจะอนุญาตให้ใช้ไมโครโฟนได้

#### ขั้นตอนที่ 2: สร้าง Frontend Build-time Configuration

Next.js ต้องการตัวแปร `NEXT_PUBLIC_*` ในขั้นตอน **build time**. ให้สร้างไฟล์ `.env.production` ในโฟลเดอร์ `frontend/`:

```bash
cd /path/to/servio/frontend
echo "NEXT_PUBLIC_WEBSOCKET_ENDPOINT=wss://yourdomain.com/ws" > .env.production
cd ..
```

#### ขั้นตอนที่ 3: ตั้งค่า SSL/HTTPS ด้วย Caddy (แนะนำ)

Caddy จะจัดการเรื่อง SSL certificate (Let's Encrypt) และการต่ออายุให้อัตโนมัติ

##### การติดตั้ง (Debian/Ubuntu):
*(ดูคำสั่งติดตั้งละเอียดใน English section หรือเว็บ Caddy)*

##### สร้าง Caddyfile:
```bash
sudo nano /etc/caddy/Caddyfile
```

ใส่ Config (แก้ `yourdomain.com` เป็นของคุณ):

```caddy
yourdomain.com {
    # Caddy จัดการ SSL ให้เอง

    # Frontend (Next.js)
    reverse_proxy localhost:3000

    # WebSocket endpoint
    handle /ws {
        reverse_proxy localhost:8000 {
            header_up Upgrade {http.request.header.Upgrade}
            header_up Connection {http.request.header.Connection}
        }
    }

    # API endpoints
    handle /api/* {
        reverse_proxy localhost:8000
    }

    # Static assets
    handle /assets/* {
        reverse_proxy localhost:8000
    }
}
```

ตรวจสอบและเริ่มทำงาน:
```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable caddy
sudo systemctl start caddy
```

#### ขั้นตอนที่ 4: Build และ Deploy Application

```bash
cd /path/to/servio

# Build และ recreate ทั้ง stack
./services.sh rebuild --no-cache

# หรือ update จาก GitHub แล้ว deploy
./services.sh update
```

#### ขั้นตอนที่ 5: ตรวจสอบการ Deployment

1. **เช็ค SSL**: เข้า `https://yourdomain.com` ต้องขึ้นแม่กุญแจ
2. **เช็ค WebSocket**: เปิด Console (F12) ต้องไม่มี Error แดงๆ และต่อ `wss://...` สำเร็จ
3. **เช็คไมโครโฟน**: กดปุ่มโทร Browser ต้องขออนุญาตใช้ไมค์ และปุ่มต้องกดได้ (สีเขียว)

#### ปัญหาที่พบบ่อย (Common Issues)

**ปัญหา 1: ปุ่มโทรเป็นสีเทา กดไม่ได้**
- **สาเหตุ**: WebSocket เชื่อมต่อไม่ได้ หรือ Mixed Content
- **แก้**: เช็ค `.env.production` ใน frontend ว่าเป็น `wss://` ถูกต้องไหม แล้ว Build frontend ใหม่

**ปัญหา 2: ไมโครโฟนใช้ไม่ได้ / Browser บล็อก**
- **สาเหตุ**: เข้าเว็บผ่าน `http://` ธรรมดา
- **แก้**: ต้องเข้าผ่าน `https://` เท่านั้น

**ปัญหา 3: WebSocket Error**
- **Console แจ้ง**: `requested insecure content from ws://localhost:8000/ws`
- **แก้**: Frontend ยังจำค่าเก่าที่เป็น localhost อยู่ ให้แก้ `.env` เป็นโดเมนจริง แลัว Rebuild

#### Checklist ความปลอดภัย
- [ ] ตั้งรหัสผ่าน Database ให้ยาก
- [ ] เปิด HTTPS/SSL
- [ ] ตั้งค่า `ENVIRONMENT=production`
- [ ] ตั้ง `ALLOWED_ORIGINS` ให้รับเฉพาะโดเมนเรา
- [ ] ใช้ `wss://` สำหรับ WebSocket
- [ ] Backup Database สม่ำเสมอ
- [ ] ตั้งค่า `ALLOWED_ORIGINS` ให้ครอบคลุม `https://yourdomain.com`

---

### โครงสร้างความปลอดภัยแบบใหม่ (Security Hardening & Infrastructure)

ระบบปัจจุบันถูกปรับปรุงให้มีความปลอดภัยระดับ Enterprise ดังนี้:

- **Reverse Proxy (Nginx)**: บริการทั้งหมดถูกซ่อนไว้หลัง Nginx Proxy (Port 80/443)
- **SSL by Default**: รองรับ HTTPS และ WSS (Secure WebSocket) พร้อมระบบสร้าง Self-signed certificate อัตโนมัติใน `services.sh`
- **Service Isolation**: พอร์ตภายใน (3000, 8000, 5432) จะไม่ถูกเปิดออกสู่ภายนอก เข้าถึงได้เฉพาะผ่าน Proxy เท่านั้น
- **Read-only Filesystem**: Backend container ทำงานในโหมด Read-only เพื่อป้องกันการเขียนไฟล์ไม่พึงประสงค์ โดยมีการแยก `tmpfs` สำหรับงานชั่วคราว
- **Unified Origin**: Frontend และ Backend ทำงานบนโดเมนและพอร์ตเดียวกัน ลดปัญหา CORS และ Mixed Content

**ช่องทางการเข้าใช้งานแบบใหม่:**
- **Frontend & Admin**: `https://localhost`
- **Backend API**: `https://localhost/api`
- **WebSocket**: `wss://localhost/ws`

---

## การใช้งาน Admin & Agents

### Admin Console
- เข้าที่: `http://localhost:3001/admin` (หรือพอร์ตอื่นใน dev mode)
- ล็อกอิน: `admin` (รหัสผ่านตามที่ตั้งใน DB; token จะถูกจำไว้ใน browser)

### การจัดการ Agents (Agents Management)
มี 2 แท็บหลัก:

#### 1. **Agents Tab**
- สร้าง/แก้ไข/ลบ Agent ทั่วไป
- ใส่คำสั่ง (Instructions), เลือกรุ่นโมเดล, ใส่ Tools
- ตั้งค่าการส่งต่อ (Handoffs)
- ทดสอบคุยกับ Agent ได้เลยตรงนั้น

#### 2. **File Store Agents Tab**
- สร้าง Agent ค้นหาเอกสารด้วย Gemini
- อัปโหลดไฟล์ จัดการไฟล์
- สร้าง Tool ค้นหาให้อัตโนมัติ (Auto-create tools)
- ทดสอบคำถามพร้อมดูแหล่งอ้างอิง

### Dynamic Coordinator + DB Agents
- ระบบจะสร้าง Coordinator agent ขึ้นมาตอน Run time โดยรวมเอา Agent ที่มีใน Database เข้าไปเป็นเงื่อนไขการส่งต่อ (Handoffs) ด้วย
- ถ้าคุณสร้าง "Dtwin Agent" ใน Admin, ตัว Coordinator ก็จะส่งต่อให้ได้เมื่อ User ถามถึง DTWIN
- File Store Agent tools ที่สร้างไว้ ทุก Agent สามารถดึงไปใช้ได้

### Dtwin Agent Tips
- สำหรับการทำ Offline/Dev environment ให้ปิด MCP tools เพื่อไม่ให้ Error:
  - เพิ่มใน `.env`: `DISABLE_MCP=1`
- ถ้าจะเทส Dtwin แบบไม่ต่อ Network ให้รัน: `uv run python server/scripts/configure_dtwin_fallback.py` (จะเปลี่ยนไปใช้ Mock tool แทน)

## Screenshots & GIFs

### Admin Dashboard
หน้าแดชบอร์ดแสดงภาพรวมระบบพร้อมสถิติเรียลไทม์

![Admin Dashboard](dashboard-preview.png)

**ฟีเจอร์เด่น:**
- **System Overview**: ดูจำนวน Agent, Tool ทั้งหมด
- **Quick Actions**: ปุ่มลัดสร้าง Agent หรือ Tool ใหม่
- **Clean Interface**: ดีไซน์ทันสมัย ใช้งานง่าย
- **เมนูจัดการ**: แถบด้านซ้ายสำหรับเข้าถึงฟังก์ชันต่างๆ

### Dtwin Transfer (การส่งต่องาน)
ภาพตัวอย่างการที่ User ถามถึง DTWIN แล้วระบบส่งต่อไปยัง Dtwin Agent:

![Dtwin transfer](docs/images/dtwin-transfer.png)

### Admin Tool Form (MCP)
![MCP tool form](.playwright-mcp/mcp-tool-form.png)

### Admin Settings Saved
![Admin settings success](.playwright-mcp/admin-settings-success.png)

## การใช้งานแอปพลิเคชัน (Using the App)

### อินเทอร์เฟซแบบ Push-to-Talk

1. **เริ่มโทร**: กดปุ่มโทรสีเขียว 🟢
2. **ปุ่มพูดจะปรากฏ**: ปุ่มไมโครโฟนสีฟ้าใหญ่ๆ
3. **กดค้างเพื่อพูด**:
   - กดปุ่มค้างไว้ (คลิกเมาส์ หรือแตะหน้าจอ)
   - ปุ่มเปลี่ยนเป็นสีแดง 🔴 และขึ้นว่า "Recording..."
   - พูดข้อความของคุณ
4. **ปล่อยเพื่อส่ง**:
   - ปล่อยปุ่มเมื่อพูดจบ
   - เสียงจะถูกส่งไปประมวลผลทันที
   - ปุ่มกลับเป็นสีฟ้า พร้อมรับคำสั่งต่อไป
5. **วางสาย**: กดปุ่มวางสายสีแดง เพื่อจบการทำงาน

### Console Debugging
กด F12 เพื่อดู Log การทำงานได้:
```
📞 Call started - Ready for Push-to-Talk
🎤 Push-to-Talk: Recording started
🛑 Push-to-Talk: Recording stopped
📤 Sending audio, length: 48000
Transferred to Stylist Agent
📞 Call ended
```

### ตัวอย่างบทสนทนา

**ขอคำแนะนำแฟชั่น**:
```
คุณ: [กดค้าง] "หน้าร้อนใส่ชุดอะไรดี?"
Stylist Agent: "แนะนำเสื้อยืดผ้าฝ้ายระบายอากาศครับ..."

คุณ: [กดค้าง] "ขอเทรนด์ในกรุงเทพฯ ช่วงนี้หน่อย"
Stylist Agent: [Uses WebSearch] "เทรนด์ตอนนี้ที่กำลังมาคือ..."
```

**จัดการคำสั่งซื้อ**:
```
คุณ: [กดค้าง] "เช็ครายการสั่งซื้อให้หน่อย"
→ Transferred to Customer Support Agent
Customer Support: "คุณมี 9 รายการครับ ล่าสุดคือ AB472..."

คุณ: [กดค้าง] "ขอคืนเงินรายการ AB472"
Customer Support: [Uses submit_refund_request] "ดำเนินการคืนเงินให้เรียบร้อยครับ"
```

## Contributing

ยินดีต้อนรับทุก Issues และ Pull Requests เพื่อปรับปรุงแอปพลิเคชันนี้

## License

โปรเจกต์นี้ใช้สัญญาอนุญาตแบบ MIT ดูรายละเอียดในไฟล์ LICENSE
