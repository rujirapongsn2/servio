# คู่มือการติดตั้ง Widget พร้อม API Key Authentication

## ภาพรวม

Widget ของ Servio ตอนนี้มีระบบ authentication ด้วย API Key เพื่อป้องกันการใช้งานโดยไม่ได้รับอนุญาต คู่มือนี้จะแนะนำวิธีการสร้าง API Key และติดตั้ง Widget บนเว็บไซต์ของคุณ

## ขั้นตอนที่ 1: เข้าสู่ระบบ Admin Panel

1. เปิดเบราว์เซอร์ไปที่ `https://your-domain.com/admin/login`
2. Login ด้วย admin username และ password
3. เมื่อ login สำเร็จ คุณจะได้รับ JWT token ที่เก็บไว้ใน localStorage

## ขั้นตอนที่ 2: สร้าง API Key สำหรับ Widget

1. ไปที่หน้า **Widget Generator**: `https://your-domain.com/admin/tools/widget`
2. ในส่วน **API Keys** ด้านบน คุณจะเห็น:
   - รายการ API keys ที่มีอยู่ (ถ้ามี)
   - ฟอร์มสร้าง API key ใหม่

### สร้าง API Key ใหม่:

1. กรอก **Key Name** (ชื่อเพื่อจำได้ง่าย):
   - ตัวอย่าง: "Production Widget", "Staging Website", "Marketing Site"

2. (Optional) กรอก **Expires in (days)**:
   - ระบุจำนวนวันที่ต้องการให้ key หมดอายุ
   - เว้นว่างไว้ถ้าไม่ต้องการให้หมดอายุ
   - แนะนำ: 365 วัน (1 ปี) สำหรับ production

3. กด **Create API Key**

4. **สำคัญมาก!** จะมี popup แสดง API key ที่สร้างขึ้น:
   ```
   API Key created successfully!

   sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

   The key has been copied to your clipboard.
   Save it now - it won't be shown again!
   ```

5. **บันทึก API key นี้ทันที!** เพราะจะไม่สามารถดูได้อีก
   - Key จะถูก copy ไว้ใน clipboard แล้ว
   - แนะนำให้เก็บไว้ใน password manager หรือ environment variables

## ขั้นตอนที่ 3: เลือก API Key และ Config Widget

1. หลังจากสร้าง API key แล้ว จะมีรายการ API key ปรากฏ
2. กดปุ่ม **Select** ที่ API key ที่ต้องการใช้
3. API key ที่เลือกจะถูกแสดงพร้อมสถานะ "Selected"
4. Config widget ตามต้องการ:
   - **Widget Type**: Voice Agent หรือ Chat Text Message
   - **Position**: Bottom Right หรือ Bottom Left
   - **Allow Toggle**: ให้ user สลับระหว่าง voice กับ text ได้หรือไม่

## ขั้นตอนที่ 4: Copy Embed Code

ในส่วน **Generated Code** คุณจะเห็น embed code พร้อม API key ที่เลือกไว้แล้ว:

```html
<script src="https://your-domain.com/embed.js"
        data-position="bottom-right"
        data-type="voice"
        data-allow-toggle="true"
        data-server-url="https://your-domain.com"
        data-api-key="sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx">
</script>
```

กดปุ่ม **Copy Code** เพื่อ copy code

## ขั้นตอนที่ 5: ติดตั้งบนเว็บไซต์

1. เปิดไฟล์ HTML ของเว็บไซต์
2. วางโค้ดที่ copy มาก่อน tag `</body>` ปิด:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Your Website</title>
</head>
<body>
    <!-- Your website content -->

    <!-- Servio Widget - วางตรงนี้ -->
    <script src="https://your-domain.com/embed.js"
            data-position="bottom-right"
            data-type="voice"
            data-allow-toggle="true"
            data-server-url="https://your-domain.com"
            data-api-key="sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx">
    </script>
</body>
</html>
```

3. บันทึกไฟล์และ deploy

## การจัดการ API Keys

### ดู API Keys ทั้งหมด

ในหน้า Widget Generator จะแสดงรายการ API keys พร้อมข้อมูล:
- **Name**: ชื่อของ key
- **Status**: Active (สีเขียว) หรือ Inactive (สีเทา)
- **API Key**: key เต็ม (สามารถ copy ได้)
- **Usage**: จำนวนครั้งที่ใช้งาน
- **Last Used**: วันที่ใช้งานล่าสุด
- **Expires**: วันที่หมดอายุ (ถ้ามี)

### เปิด/ปิดการใช้งาน (Enable/Disable)

1. หา API key ที่ต้องการในรายการ
2. กดปุ่ม **Disable** เพื่อปิดการใช้งานชั่วคราว
3. Key ที่ถูก disable จะไม่สามารถใช้งานได้ทันที
4. กด **Enable** เพื่อเปิดใช้งานอีกครั้ง

### ลบ API Key

1. หา API key ที่ต้องการลบ
2. กดปุ่ม **Delete** (สีแดง)
3. ยืนยันการลบ
4. **คำเตือน**: การลบไม่สามารถย้อนกลับได้!

### Copy API Key อีกครั้ง

1. หา API key ในรายการ
2. กดปุ่ม **Copy** ข้าง API key
3. Key จะถูก copy ไปยัง clipboard

## การทดสอบ Widget

1. ที่หน้า Widget Generator
2. ในส่วน **Preview** กดปุ่ม **Test Widget**
3. จะเปิดหน้าทดสอบ widget ใหม่
4. ลองใช้งานทั้ง voice และ text chat

## Troubleshooting

### Widget ไม่แสดงหรือ error

**ตรวจสอบ API Key:**
- API key ต้อง active (ไม่ถูก disable)
- API key ต้องไม่หมดอายุ
- API key ต้องถูกต้อง (ไม่มีการพิมพ์ผิด)

**ตรวจสอบ Console:**
```javascript
// เปิด Browser Console (F12)
// ถ้าเห็น error เหล่านี้:
"API key is required"
// → ไม่มี API key ใน embed code

"Invalid or expired API key"
// → API key ไม่ถูกต้องหรือหมดอายุ
```

**วิธีแก้:**
1. ไปที่ Widget Generator
2. สร้าง API key ใหม่
3. Copy embed code ใหม่
4. Replace code บนเว็บไซต์

### Widget ใช้งานช้า

- ตรวจสอบ **Usage Count** ของ API key
- ถ้ามีการใช้งานผิดปกติ (จำนวนมากเกินไป) อาจมีคนใช้ key ของคุณ
- แนะนำให้:
  1. Disable API key เดิม
  2. สร้าง API key ใหม่
  3. Update embed code

### API Key หาย

- API key ไม่สามารถดูซ้ำได้หลังจากสร้าง
- ถ้าหาย ต้องสร้างใหม่และ update embed code ทุกที่ที่ใช้งาน

## Best Practices

### สำหรับ Production

1. **ตั้งชื่อ Key ให้ชัดเจน**:
   ```
   Production - Main Website
   Production - Landing Page
   Staging - Test Site
   ```

2. **กำหนดวันหมดอายุ**:
   - Production: 365 วัน (rotate ทุกปี)
   - Staging: 90 วัน
   - Development: 30 วัน

3. **Rotate Keys เป็นระยะ**:
   - สร้าง key ใหม่ทุก ๆ 3-6 เดือน
   - Update embed code
   - ลบ key เก่าหลัง deploy สำเร็จ

4. **Monitor Usage**:
   - ตรวจสอบ usage count เป็นประจำ
   - ถ้าเพิ่มขึ้นผิดปกติ อาจมีปัญหา

### สำหรับหลาย Environments

สร้าง API key แยกกันสำหรับแต่ละ environment:

```
API Key สำหรับ Production:    sk_prod_xxx...
API Key สำหรับ Staging:       sk_staging_xxx...
API Key สำหรับ Development:   sk_dev_xxx...
```

ประโยชน์:
- ควบคุมการเข้าถึงแต่ละ environment
- Disable ได้เฉพาะ environment ที่ต้องการ
- ติดตาม usage แยกกันได้

## Support

หากมีปัญหาหรือคำถาม:
1. ตรวจสอบเอกสารฉบับนี้ก่อน
2. ดู log ใน Browser Console (F12)
3. ตรวจสอบสถานะ API key ในหน้า Widget Generator
4. ติดต่อทีมพัฒนา

---

**เอกสารนี้อัพเดตล่าสุด**: 2025-12-24
