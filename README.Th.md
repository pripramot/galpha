# galpha  Agent/Toolkit สำหรับ GeoJSON OSINT (ไทย)

galpha ประกอบด้วย agent สำหรับตรวจ/วิเคราะห์ GeoJSON (galpha-agent) และสคริปต์ช่วยแปลงข้อมูลภาคสนาม

การทดสอบ agent (Gemini CLI):
```
gemini run-agent --manifest agents/galpha-agent.yaml --input samples/input_with_options.json
```

ไฟล์สำคัญ:
- agents/galpha-agent.yaml — manifest ของ agent
- agents/galpha_agent_tools.py — ฟังก์ชันประมวลผล
- scripts/csv_to_geojson.py — แปลง CSV → GeoJSON
- samples/ — ตัวอย่างไฟล์สำหรับทดสอบ

ข้อควรระวัง:
- อย่า commit secrets ลง repo ตรงๆ
- Mask พิกัดชนิดเสี่ยงก่อนเผยแพร่
