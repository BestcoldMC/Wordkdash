import streamlit as st
import pandas as pd
from supabase import create_client, Client
from PIL import Image
import io
import uuid
from datetime import datetime

# ---------------------------
# 1. เชื่อมต่อ Supabase
# ---------------------------
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

BUCKET_NAME = "work_images"

# ---------------------------
# 2. ฟังก์ชัน CRUD + อัปโหลดรูป
# ---------------------------
def upload_image(file) -> str | None:
    if not file:
        return None
    ext = file.name.split('.')[-1]
    file_name = f"{uuid.uuid4()}.{ext}"
    try:
        supabase.storage.from_(BUCKET_NAME).upload(file_name, file.getvalue())
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(file_name)
        return public_url
    except Exception as e:
        st.error(f"อัปโหลดรูปไม่สำเร็จ: {e}")
        return None

def get_all_data(machine_filter=None):
    response = supabase.table("work_updates").select("*").order("created_at", desc=False).execute()
    df = pd.DataFrame(response.data)
    if df.empty:
        return df
    if machine_filter and machine_filter != "ทั้งหมด":
        df = df[df["machine"] == machine_filter]
    return df

def add_update(date, month, machine, detail, image_file):
    image_url = upload_image(image_file)
    data = {
        "date": date,
        "month": month,
        "machine": machine,
        "detail": detail,
        "image_url": image_url
    }
    supabase.table("work_updates").insert(data).execute()
    st.success("✅ เพิ่มข้อมูลสำเร็จ")
    st.rerun()

def update_update(id, date, month, machine, detail, image_file):
    old = supabase.table("work_updates").select("*").eq("id", id).execute()
    if old.data:
        old_url = old.data[0].get("image_url")
    else:
        old_url = None

    new_image_url = upload_image(image_file) if image_file else old_url
    data = {
        "date": date,
        "month": month,
        "machine": machine,
        "detail": detail,
        "image_url": new_image_url
    }
    supabase.table("work_updates").update(data).eq("id", id).execute()
    st.success("✏️ อัปเดตข้อมูลสำเร็จ")
    st.rerun()

def delete_update(id):
    supabase.table("work_updates").delete().eq("id", id).execute()
    st.success("🗑️ ลบข้อมูลสำเร็จ")
    st.rerun()

# ---------------------------
# 3. หน้า Dashboard
# ---------------------------
def dashboard_page():
    st.title("📊 Dashboard อัปเดตงานประจำสัปดาห์")

    df = get_all_data()
    if df.empty:
        st.info("ยังไม่มีข้อมูลในระบบ")
        return

    machines = ["ทั้งหมด"] + sorted(df["machine"].unique().tolist())
    selected_machine = st.sidebar.selectbox("🔍 กรองตามเครื่องจักร", machines)

    filtered_df = get_all_data(selected_machine if selected_machine != "ทั้งหมด" else None)
    
    st.subheader(f"📋 รายการงาน ({len(filtered_df)} รายการ)")
    
    display_df = filtered_df.copy()
    if not display_df.empty:
        display_df["วันที่"] = display_df["date"].astype(str) + "/" + display_df["month"].astype(str)
        display_df["รายละเอียด (ย่อ)"] = display_df["detail"].apply(lambda x: x[:80] + "..." if pd.notna(x) and len(x) > 80 else x)
        
        st.dataframe(
            display_df[["id", "machine", "วันที่", "รายละเอียด (ย่อ)", "image_url"]],
            column_config={
                "id": "ID",
                "machine": "เครื่องจักร",
                "วันที่": "วันที่",
                "รายละเอียด (ย่อ)": "รายละเอียด",
                "image_url": st.column_config.ImageColumn("รูปภาพ", width="small")
            },
            use_container_width=True,
            hide_index=True
        )
        
        st.markdown("### 🔔 รายการที่ควรติดตาม")
        important_keywords = ["รอ", "Breakdown", "ปัญหา", "ไม่เสถียร", "Bevel", "ซ่อม"]
        mask = display_df["detail"].apply(lambda x: any(kw in str(x) for kw in important_keywords))
        important_df = display_df[mask]
        if not important_df.empty:
            for _, row in important_df.iterrows():
                with st.expander(f"⚠️ {row['machine']} - {row['detail'][:100]}..."):
                    st.write(row['detail'])
                    if row['image_url']:
                        st.image(row['image_url'], width=200)
        else:
            st.success("ไม่มีรายการเร่งด่วนในขณะนี้")

# ---------------------------
# 4. หน้า Admin (CRUD)
# ---------------------------
def admin_page():
    st.title("👑 หน้าแอดมิน - จัดการข้อมูล")
    
    password = st.text_input("รหัสผ่านผู้ดูแลระบบ", type="password")
    if password != st.secrets["ADMIN_PASSWORD"]:
        st.warning("กรุณากรอกรหัสผ่านที่ถูกต้อง")
        return

    st.success("เข้าสู่ระบบสำเร็จ")
    
    tab1, tab2 = st.tabs(["➕ เพิ่มงานใหม่", "✏️ แก้ไข / ลบ งาน"])

    with tab1:
        with st.form("add_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_date = st.number_input("วันที่ (1-31)", min_value=1, max_value=31, step=1)
                new_month = st.number_input("เดือน (1-12)", min_value=1, max_value=12, step=1)
            with col2:
                new_machine = st.selectbox("เครื่องจักร", ["LP1", "LP2", "RC1", "RC2", "RC3", "HB3", "WR1"])
            new_detail = st.text_area("รายละเอียด")
            new_image = st.file_uploader("อัปโหลดรูปภาพ (ถ้ามี)", type=["jpg", "jpeg", "png"])
            submitted = st.form_submit_button("บันทึกข้อมูล")
            if submitted:
                if not new_detail.strip():
                    st.error("กรุณากรอกรายละเอียด")
                else:
                    add_update(new_date, new_month, new_machine, new_detail, new_image)

    with tab2:
        df_all = get_all_data()
        if df_all.empty:
            st.info("ไม่มีข้อมูลในระบบ")
            return
        
        id_list = df_all["id"].tolist()
        selected_id = st.selectbox("เลือก ID ที่ต้องการแก้ไข/ลบ", id_list, format_func=lambda x: f"ID {x} - {df_all[df_all['id']==x]['machine'].iloc[0]}")
        selected_row = df_all[df_all["id"] == selected_id].iloc[0]
        
        with st.form("edit_form"):
            col1, col2 = st.columns(2)
            with col1:
                edit_date = st.number_input("วันที่", value=int(selected_row["date"]), min_value=1, max_value=31)
                edit_month = st.number_input("เดือน", value=int(selected_row["month"]), min_value=1, max_value=12)
            with col2:
                edit_machine = st.selectbox("เครื่องจักร", ["LP1","LP2","RC1","RC2","RC3","HB3","WR1"], index=["LP1","LP2","RC1","RC2","RC3","HB3","WR1"].index(selected_row["machine"]))
            edit_detail = st.text_area("รายละเอียด", value=selected_row["detail"] or "")
            edit_image = st.file_uploader("เปลี่ยนรูปภาพ (ถ้าไม่ต้องการเปลี่ยนให้เว้นว่าง)", type=["jpg","jpeg","png"])
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.form_submit_button("💾 อัปเดตข้อมูล"):
                    if not edit_detail.strip():
                        st.error("รายละเอียดห้ามว่าง")
                    else:
                        update_update(selected_id, edit_date, edit_month, edit_machine, edit_detail, edit_image)
            with col_btn2:
                if st.form_submit_button("🗑️ ลบข้อมูลนี้", type="primary"):
                    delete_update(selected_id)
        
        if selected_row["image_url"]:
            st.image(selected_row["image_url"], caption="รูปปัจจุบัน", width=200)

# ---------------------------
# 5. ใส่ข้อมูลเริ่มต้นจาก Excel
# ---------------------------
def seed_initial_data():
    if get_all_data().empty:
        initial_records = [
            {"date": 18, "month": 5, "machine": "LP1", "detail": "-"},
            {"date": 18, "month": 5, "machine": "LP2", "detail": "- ปัญหา Breakdown เนื่องจากตัดแล้วลำแสงไม่เสถียร แก้ไขโดยการเปลี่ยน Protective lens เนื่องจากมีรอยเกิดขึ้น หลังจากเปลี่ยนแล้วสามารถตัดได้ ทำการติดตามอาการอยู่ครับ\n- ปัญหารอยตัดเอียง Bevel ที่มีลักษณะเว้ามุมเดียว ส่งผลให้ไม่ผ่านมาตรฐานงานลูกค้าเนื่องจาก มี gap เกิน 1 mm. ทางทาเคโกะแจ้งว่าช่างจีนเข้าพุธที่ 20/5 โดยมีแผนที่จะนำหัวตัดของทาเคโกะมาใส่แล้วทดสอบการตัดว่ายังมีอาการเว้าอยู่หรือไม่"},
            {"date": 18, "month": 5, "machine": "RC1", "detail": "-"},
            {"date": 18, "month": 5, "machine": "RC2", "detail": "-"},
            {"date": 18, "month": 5, "machine": "RC3", "detail": "- งานซ่อมตัวดันเหล็กป้อนเข้าเครื่องตัวที่ 1  ค้าง เบื้องต้นแก้ไขโดยการนำตัวกลางไปใส่แทนแต่ยังไม่มีการซ่อมกลับมาใช้งาน"},
            {"date": 18, "month": 5, "machine": "HB3", "detail": "- หลังจากย้ายเครื่องจักร ผลิตงานปกติครับ"},
            {"date": 18, "month": 5, "machine": "WR1", "detail": "- รออัพเดท concept จาก เลิศวิลัยแจ้งว่าภายในสัปดาห์น้จะส่งข้อมูลมาให้ครับ\n- ลวดเชื่อม Spec ใหม่ทำการทดสอบไปแล้ว  1 ม้วน ( 15 kg ได้ชิ้นงาน 264 Pc) กำลังสั่งซื้อเพิ่มอีกจำนวน 3 ม้วนมาทดสอบ หากไม่พบปัญหาจะดำเนินการสั่งซื้อถังใหญ่ 250 kg ครับ"}
        ]
        for rec in initial_records:
            supabase.table("work_updates").insert(rec).execute()
        st.success("✅ โหลดข้อมูลตัวอย่างจากไฟล์ Excel เรียบร้อยแล้ว (เฉพาะครั้งแรก)")

# ---------------------------
# 6. Main UI
# ---------------------------
def main():
    st.set_page_config(page_title="Work Update Dashboard", layout="wide")
    seed_initial_data()
    
    st.sidebar.title("📌 เมนูหลัก")
    page = st.sidebar.radio("ไปที่", ["📊 Dashboard", "👑 Admin"])
    
    if page == "📊 Dashboard":
        dashboard_page()
    else:
        admin_page()

if __name__ == "__main__":
    main()
