import os
import sqlite3
from datetime import datetime, date, time, timedelta
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

# =========================================================
# NHÀ HÀNG CỎ BỐN LÁ - BÁN HÀNG, HÓA ĐƠN, DOANH THU, AI
# =========================================================

st.set_page_config(
    page_title="Nhà Hàng Cỏ Bốn Lá",
    page_icon="🍀",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "co_bon_la.db"
LOGO_PATH = BASE_DIR / "Logo1.JPG"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

FREE_MODELS = [
    "google/gemini-2.5-flash:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
]

DEFAULT_MENU = [
    ("Gỏi cuốn", "Khai vị", 45000, "Phần"),
    ("Khoai tây chiên", "Khai vị", 35000, "Phần"),
    ("Cơm chiên Dương Châu", "Món chính", 65000, "Phần"),
    ("Gà nướng", "Món chính", 180000, "Phần"),
    ("Bò lúc lắc", "Món chính", 145000, "Phần"),
    ("Lẩu Thái", "Món chính", 250000, "Nồi"),
    ("Mì xào bò", "Món chính", 75000, "Phần"),
    ("Rau xào", "Món phụ", 45000, "Phần"),
    ("Coca-Cola", "Nước uống", 15000, "Lon"),
    ("Pepsi", "Nước uống", 15000, "Lon"),
    ("Nước suối", "Nước uống", 10000, "Chai"),
    ("Trà đào", "Nước uống", 30000, "Ly"),
    ("Trà tắc", "Nước uống", 25000, "Ly"),
    ("Cà phê", "Nước uống", 30000, "Ly"),
    ("Chè khúc bạch", "Tráng miệng", 35000, "Phần"),
    ("Trái cây", "Tráng miệng", 40000, "Phần"),
]


def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def table_columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_columns(conn, table, columns):
    existing = table_columns(conn, table)
    for name, sql_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def init_db():
    with connect_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS menu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Khác',
                price REAL NOT NULL DEFAULT 0,
                unit TEXT NOT NULL DEFAULT 'Phần',
                active INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_code TEXT UNIQUE,
                table_number TEXT,
                employee TEXT,
                customer TEXT,
                subtotal REAL DEFAULT 0,
                discount REAL DEFAULT 0,
                service_charge REAL DEFAULT 0,
                vat REAL DEFAULT 0,
                total REAL DEFAULT 0,
                payment_method TEXT,
                received REAL DEFAULT 0,
                change_money REAL DEFAULT 0,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                menu_id INTEGER,
                item_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit_price REAL NOT NULL DEFAULT 0,
                amount REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
            )
        """)

        # Bổ sung các cột còn thiếu cho database cũ, không xóa dữ liệu.
        ensure_columns(conn, "invoices", {
            "invoice_code": "TEXT", "table_number": "TEXT", "employee": "TEXT",
            "customer": "TEXT", "subtotal": "REAL DEFAULT 0", "discount": "REAL DEFAULT 0",
            "service_charge": "REAL DEFAULT 0", "vat": "REAL DEFAULT 0",
            "total": "REAL DEFAULT 0", "payment_method": "TEXT", "received": "REAL DEFAULT 0",
            "change_money": "REAL DEFAULT 0", "created_at": "TEXT"
        })
        ensure_columns(conn, "invoice_items", {
            "invoice_id": "INTEGER", "menu_id": "INTEGER", "item_name": "TEXT",
            "quantity": "INTEGER DEFAULT 1", "unit_price": "REAL DEFAULT 0",
            "amount": "REAL DEFAULT 0"
        })

        count = conn.execute("SELECT COUNT(*) FROM menu").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO menu(name, category, price, unit, active) VALUES (?, ?, ?, ?, 1)",
                DEFAULT_MENU,
            )


def money(value):
    try:
        return f"{float(value or 0):,.0f} đ".replace(",", ".")
    except (TypeError, ValueError):
        return "0 đ"


def new_invoice_code():
    return "CBL-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def get_menu(active_only=True):
    with connect_db() as conn:
        query = "SELECT * FROM menu"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY category, name"
        return [dict(row) for row in conn.execute(query).fetchall()]


def save_invoice(info, cart):
    if not cart:
        raise ValueError("Hóa đơn chưa có món.")

    conn = connect_db()
    try:
        with conn:
            cur = conn.execute("""
                INSERT INTO invoices (
                    invoice_code, table_number, employee, customer, subtotal, discount,
                    service_charge, vat, total, payment_method, received, change_money, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                info["invoice_code"], info["table"], info["employee"], info["customer"],
                info["subtotal"], info["discount"], info["service"], info["vat"],
                info["total"], info["payment"], info["received"], info["change"],
                info["created_at"],
            ))
            invoice_id = cur.lastrowid
            conn.executemany("""
                INSERT INTO invoice_items (
                    invoice_id, menu_id, item_name, quantity, unit_price, amount
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, [
                (invoice_id, item["id"], item["name"], item["quantity"],
                 item["price"], item["amount"])
                for item in cart
            ])
        return invoice_id
    finally:
        conn.close()


def get_api_key():
    # Ưu tiên Streamlit Secrets, sau đó biến môi trường.
    try:
        secret_key = st.secrets.get("OPENROUTER_API_KEY", "")
    except Exception:
        secret_key = ""
    return str(secret_key or os.getenv("OPENROUTER_API_KEY", "")).strip()


def call_openrouter(api_key, messages, model):
    if not api_key:
        return (
            "Chưa cấu hình API Key. Trên Streamlit Cloud, vào **Settings → Secrets** "
            "và thêm `OPENROUTER_API_KEY = \"YOUR_NEW_KEY\"`. "
            "Không dán key vào code hoặc gửi key trong chat."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://co-bon-la.streamlit.app",
        "X-Title": "Co Bon La Restaurant",
    }
    payload = {"model": model, "messages": messages, "temperature": 0.5}

    try:
        response = requests.post(
            OPENROUTER_URL, headers=headers, json=payload, timeout=45
        )
        if response.status_code == 200:
            data = response.json()
            choices = data.get("choices", [])
            if choices and choices[0].get("message", {}).get("content"):
                return choices[0]["message"]["content"]
            return "OpenRouter đã phản hồi nhưng không có nội dung trả lời."
        if response.status_code == 401:
            return "Lỗi 401: API Key không hợp lệ hoặc đã bị thu hồi. Hãy tạo key mới và cập nhật Secrets."
        if response.status_code == 402:
            return "Lỗi 402: tài khoản hoặc hạn mức không cho phép gọi mô hình này. Hãy kiểm tra hạn mức và chọn mô hình :free."
        if response.status_code == 429:
            return "Lỗi 429: đã vượt hạn mức/tốc độ gọi. Hãy chờ rồi thử lại hoặc chọn mô hình miễn phí khác."
        if response.status_code == 404:
            return "Lỗi 404: mô hình không khả dụng hoặc tên mô hình không đúng. Hãy chọn mô hình khác trong danh sách."
        try:
            detail = response.json().get("error", {}).get("message", response.text)
        except Exception:
            detail = response.text
        return f"Lỗi OpenRouter ({response.status_code}): {str(detail)[:600]}"
    except requests.Timeout:
        return "Kết nối OpenRouter quá thời gian chờ. Vui lòng thử lại."
    except requests.RequestException as exc:
        return f"Không kết nối được OpenRouter: {exc}"


def get_restaurant_summary():
    with connect_db() as conn:
        menu_rows = conn.execute(
            "SELECT name, category, price, unit FROM menu WHERE active = 1 ORDER BY category, name"
        ).fetchall()
        rev = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total), 0) AS revenue FROM invoices"
        ).fetchone()
        top = conn.execute("""
            SELECT item_name, SUM(quantity) AS qty
            FROM invoice_items GROUP BY item_name ORDER BY qty DESC LIMIT 5
        """).fetchall()

    menu_text = "\n".join(
        f"- {r['name']} | nhóm {r['category']} | {money(r['price'])}/{r['unit']}"
        for r in menu_rows
    ) or "Menu đang trống."
    top_text = ", ".join(f"{r['item_name']} ({r['qty']})" for r in top) or "Chưa có dữ liệu."
    return (
        f"MENU ĐANG BÁN:\n{menu_text}\n\n"
        f"DỮ LIỆU THAM KHẢO: {rev['n']} hóa đơn; doanh thu tích lũy {money(rev['revenue'])}; "
        f"món bán nhiều: {top_text}."
    )


def add_to_cart(item, quantity):
    cart = st.session_state.cart
    for existing in cart:
        if existing["id"] == item["id"]:
            existing["quantity"] += int(quantity)
            existing["amount"] = existing["quantity"] * existing["price"]
            return
    cart.append({
        "id": item["id"],
        "name": item["name"],
        "price": float(item["price"]),
        "unit": item["unit"],
        "quantity": int(quantity),
        "amount": float(item["price"]) * int(quantity),
    })


init_db()

if "cart" not in st.session_state:
    st.session_state.cart = []
if "ai_messages" not in st.session_state:
    st.session_state.ai_messages = [{
        "role": "assistant",
        "content": "Xin chào! 🍀 Mình có thể gợi ý combo theo số người, sở thích và ngân sách. "
                   "Mình chỉ đề xuất các món đang có trong menu của nhà hàng."
    }]
if "last_invoice_code" not in st.session_state:
    st.session_state.last_invoice_code = None

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
.main-title {font-size: 2rem; font-weight: 800; color: #166534;}
div[data-testid="stMetric"] {background: #f0fdf4; border: 1px solid #bbf7d0;
    padding: 14px; border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

head_logo, head_text = st.columns([1, 6], vertical_alignment="center")
with head_logo:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=95)
    else:
        st.markdown("## 🍀")
with head_text:
    st.markdown('<div class="main-title">NHÀ HÀNG CỎ BỐN LÁ</div>', unsafe_allow_html=True)
    st.caption("Hệ thống gọi món • Quản lý hóa đơn • Báo cáo doanh thu • Trợ lý AI")
st.divider()

st.sidebar.title("🍀 CỎ BỐN LÁ")
page = st.sidebar.radio(
    "MENU HỆ THỐNG",
    ["🧾 Bán hàng", "🍽️ Quản lý món", "📜 Hóa đơn", "📊 Doanh thu", "🤖 Trợ lý AI Tư vấn"],
)
st.sidebar.caption("API Key được đọc từ Streamlit Secrets, không lưu trong code.")
if not get_api_key():
    st.sidebar.warning("Chưa cấu hình OpenRouter API Key.")

# ---------------------------------------------------------
# 1. BÁN HÀNG
# ---------------------------------------------------------
if page == "🧾 Bán hàng":
    st.subheader("🧾 TẠO HÓA ĐƠN")
    col1, col2, col3 = st.columns(3)
    table = col1.text_input("🪑 Bàn số", placeholder="Ví dụ: Bàn 05")
    employee = col2.text_input("👨‍💼 Nhân viên", placeholder="Tên nhân viên")
    customer = col3.text_input("👤 Tên khách hàng (không bắt buộc)")

    st.divider()
    st.markdown("### 🍽️ MENU MÓN ĂN")
    menu = get_menu()
    if not menu:
        st.warning("Chưa có món đang bán. Hãy thêm món trong Quản lý món.")
    else:
        categories = ["Tất cả"] + sorted({x["category"] for x in menu})
        category = st.selectbox("Nhóm món", categories)
        shown = menu if category == "Tất cả" else [x for x in menu if x["category"] == category]
        selected = st.selectbox(
            "Chọn món",
            shown,
            format_func=lambda x: f"{x['name']} — {money(x['price'])}/{x['unit']}",
        )
        a, b, c = st.columns([3, 1, 2], vertical_alignment="center")
        with a:
            st.write(f"**{selected['name']}**")
            st.caption(f"{selected['category']} • {money(selected['price'])}/{selected['unit']}")
        qty = b.number_input("Số lượng", min_value=1, max_value=999, value=1, step=1, key="sale_qty")
        with c:
            if st.button("➕ Thêm món vào hóa đơn", type="primary", use_container_width=True):
                add_to_cart(selected, qty)
                st.success(f"Đã thêm {qty} {selected['unit']} {selected['name']}.")
                st.rerun()

    st.divider()
    st.markdown("### 🛒 MÓN ĐÃ CHỌN")
    if not st.session_state.cart:
        st.info("Chưa có món nào trong hóa đơn.")
    else:
        for i, item in enumerate(st.session_state.cart):
            x1, x2, x3, x4, x5 = st.columns([3, 1, 1.5, 1.5, 0.6])
            x1.write(f"**{item['name']}**")
            x2.write(f"{item['quantity']} {item['unit']}")
            x3.write(money(item["price"]))
            x4.write(f"**{money(item['amount'])}**")
            if x5.button("🗑️", key=f"remove_{i}", help="Xóa món này"):
                st.session_state.cart.pop(i)
                st.rerun()

        subtotal = sum(x["amount"] for x in st.session_state.cart)
        left, right = st.columns(2)
        with left:
            discount = st.number_input("Giảm giá (VNĐ)", min_value=0.0, max_value=float(subtotal),
                                       value=0.0, step=1000.0)
            service_pct = st.number_input("Phí phục vụ (%)", min_value=0.0, max_value=100.0,
                                          value=0.0, step=1.0)
            vat_pct = st.number_input("VAT (%)", min_value=0.0, max_value=100.0,
                                      value=0.0, step=1.0)
        taxable_base = max(subtotal - discount, 0)
        service = taxable_base * service_pct / 100
        vat = (taxable_base + service) * vat_pct / 100
        total = max(taxable_base + service + vat, 0)

        with right:
            payment = st.selectbox("Phương thức thanh toán", ["Tiền mặt", "Chuyển khoản", "Thẻ"])
            if payment == "Tiền mặt":
                received = st.number_input("Tiền khách đưa (VNĐ)", min_value=0.0,
                                           value=float(total), step=1000.0)
            else:
                received = float(total)
                st.write(f"Khách cần thanh toán: **{money(total)}**")
            change = max(received - total, 0)

        st.markdown(f"""
        <div style="padding:18px;border-radius:14px;background:#f0fdf4;border:1px solid #bbf7d0">
          Tiền hàng: <b>{money(subtotal)}</b><br>
          Giảm giá: <b>- {money(discount)}</b><br>
          Phí phục vụ: <b>{money(service)}</b><br>
          VAT: <b>{money(vat)}</b><hr>
          <b>TỔNG THANH TOÁN</b>
          <div style="font-size:30px;color:#166534;font-weight:800">{money(total)}</div>
          Tiền thừa: <b>{money(change)}</b>
        </div>
        """, unsafe_allow_html=True)

        save_col, clear_col = st.columns([3, 1])
        if save_col.button("💾 THANH TOÁN & LƯU HÓA ĐƠN", type="primary", use_container_width=True):
            if not table.strip():
                st.error("Vui lòng nhập số bàn.")
            elif not employee.strip():
                st.error("Vui lòng nhập tên nhân viên.")
            elif discount > subtotal:
                st.error("Giảm giá không được lớn hơn tiền hàng.")
            elif payment == "Tiền mặt" and received < total:
                st.error("Tiền khách đưa chưa đủ.")
            else:
                info = {
                    "invoice_code": new_invoice_code(),
                    "table": table.strip(),
                    "employee": employee.strip(),
                    "customer": customer.strip(),
                    "subtotal": subtotal,
                    "discount": discount,
                    "service": service,
                    "vat": vat,
                    "total": total,
                    "payment": payment,
                    "received": received,
                    "change": change,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                try:
                    save_invoice(info, st.session_state.cart)
                    st.session_state.last_invoice_code = info["invoice_code"]
                    st.session_state.cart = []
                    st.success(f"Đã lưu hóa đơn {info['invoice_code']} — {money(total)}")
                    st.rerun()
                except sqlite3.Error as exc:
                    st.error(f"Không lưu được hóa đơn vào cơ sở dữ liệu: {exc}")
        if clear_col.button("🗑️ XÓA BILL", use_container_width=True):
            st.session_state.cart = []
            st.rerun()

    if st.session_state.last_invoice_code:
        st.caption(f"Hóa đơn vừa lưu gần nhất: {st.session_state.last_invoice_code}")

# ---------------------------------------------------------
# 2. QUẢN LÝ MÓN
# ---------------------------------------------------------
elif page == "🍽️ Quản lý món":
    st.subheader("🍽️ QUẢN LÝ MENU")
    tab_add, tab_list = st.tabs(["➕ Thêm món", "📋 Danh sách / chỉnh sửa"])
    categories = ["Khai vị", "Món chính", "Món phụ", "Nước uống", "Tráng miệng", "Khác"]
    units = ["Phần", "Nồi", "Đĩa", "Ly", "Lon", "Chai", "Cái"]

    with tab_add:
        with st.form("add_menu_item", clear_on_submit=True):
            name = st.text_input("Tên món")
            category = st.selectbox("Danh mục", categories)
            price = st.number_input("Giá bán (VNĐ)", min_value=0, step=1000)
            unit = st.selectbox("Đơn vị", units)
            submitted = st.form_submit_button("➕ THÊM MÓN", type="primary")
        if submitted:
            if not name.strip():
                st.error("Vui lòng nhập tên món.")
            elif price <= 0:
                st.error("Giá bán phải lớn hơn 0.")
            else:
                with connect_db() as conn:
                    conn.execute(
                        "INSERT INTO menu(name, category, price, unit, active) VALUES (?, ?, ?, ?, 1)",
                        (name.strip(), category, float(price), unit),
                    )
                st.success(f"Đã thêm món {name.strip()}.")
                st.rerun()

    with tab_list:
        foods = get_menu(active_only=False)
        if not foods:
            st.info("Chưa có món.")
        else:
            view = pd.DataFrame([{
                "ID": f["id"], "Tên món": f["name"], "Danh mục": f["category"],
                "Giá bán": money(f["price"]), "Đơn vị": f["unit"],
                "Trạng thái": "Đang bán" if f["active"] else "Ngừng bán",
            } for f in foods])
            st.dataframe(view, use_container_width=True, hide_index=True)
            chosen_id = st.selectbox(
                "Chọn món cần chỉnh sửa", [f["id"] for f in foods],
                format_func=lambda ident: next(f"{f['name']} (ID {ident})" for f in foods if f["id"] == ident),
            )
            chosen = next(f for f in foods if f["id"] == chosen_id)
            with st.form("edit_menu_item"):
                edit_name = st.text_input("Tên món", value=chosen["name"])
                edit_category = st.selectbox(
                    "Danh mục", categories,
                    index=categories.index(chosen["category"]) if chosen["category"] in categories else categories.index("Khác"),
                )
                edit_price = st.number_input("Giá bán (VNĐ)", min_value=0,
                                             value=int(chosen["price"]), step=1000)
                edit_unit = st.selectbox(
                    "Đơn vị", units,
                    index=units.index(chosen["unit"]) if chosen["unit"] in units else 0,
                )
                edit_submit = st.form_submit_button("💾 LƯU THAY ĐỔI", type="primary")
            if edit_submit:
                if not edit_name.strip():
                    st.error("Tên món không được để trống.")
                elif edit_price <= 0:
                    st.error("Giá bán phải lớn hơn 0.")
                else:
                    with connect_db() as conn:
                        conn.execute(
                            "UPDATE menu SET name=?, category=?, price=?, unit=? WHERE id=?",
                            (edit_name.strip(), edit_category, float(edit_price), edit_unit, chosen_id),
                        )
                    st.success("Đã cập nhật món.")
                    st.rerun()

            status_label = "⛔ NGỪNG BÁN" if chosen["active"] else "✅ BÁN LẠI"
            if st.button(status_label, use_container_width=True):
                with connect_db() as conn:
                    conn.execute("UPDATE menu SET active=? WHERE id=?",
                                 (0 if chosen["active"] else 1, chosen_id))
                st.rerun()

# ---------------------------------------------------------
# 3. LỊCH SỬ HÓA ĐƠN
# ---------------------------------------------------------
elif page == "📜 Hóa đơn":
    st.subheader("📜 LỊCH SỬ HÓA ĐƠN")
    search = st.text_input("Tìm theo mã hóa đơn, bàn hoặc nhân viên")
    with connect_db() as conn:
        if search.strip():
            pattern = f"%{search.strip()}%"
            invoices = conn.execute("""
                SELECT * FROM invoices
                WHERE invoice_code LIKE ? OR table_number LIKE ? OR employee LIKE ? OR customer LIKE ?
                ORDER BY id DESC
            """, (pattern, pattern, pattern, pattern)).fetchall()
        else:
            invoices = conn.execute("SELECT * FROM invoices ORDER BY id DESC LIMIT 500").fetchall()

    if not invoices:
        st.info("Chưa có hóa đơn phù hợp.")
    else:
        df = pd.DataFrame([dict(x) for x in invoices])
        show = pd.DataFrame({
            "Mã HĐ": df["invoice_code"],
            "Bàn": df["table_number"],
            "Nhân viên": df["employee"],
            "Khách hàng": df["customer"],
            "Thanh toán": df["payment_method"],
            "Tổng tiền": df["total"].apply(money),
            "Thời gian": df["created_at"],
        })
        st.dataframe(show, use_container_width=True, hide_index=True)
        options = df["invoice_code"].fillna("").tolist()
        selected_code = st.selectbox("Xem chi tiết hóa đơn", options)
        selected_invoice = df[df["invoice_code"].fillna("") == selected_code].iloc[0]
        st.markdown(f"**Mã:** {selected_code}  \n**Bàn:** {selected_invoice['table_number']}  \n"
                    f"**Nhân viên:** {selected_invoice['employee']}  \n"
                    f"**Thời gian:** {selected_invoice['created_at']}")
        with connect_db() as conn:
            items = conn.execute("""
                SELECT item_name AS 'Tên món', quantity AS 'Số lượng',
                       unit_price AS 'Đơn giá', amount AS 'Thành tiền'
                FROM invoice_items WHERE invoice_id=? ORDER BY id
            """, (int(selected_invoice["id"]),)).fetchall()
        if items:
            detail = pd.DataFrame([dict(x) for x in items])
            detail["Đơn giá"] = detail["Đơn giá"].apply(money)
            detail["Thành tiền"] = detail["Thành tiền"].apply(money)
            st.dataframe(detail, use_container_width=True, hide_index=True)
        st.write(f"Tiền hàng: **{money(selected_invoice['subtotal'])}**")
        st.write(f"Giảm giá: **{money(selected_invoice['discount'])}**")
        st.write(f"Phí phục vụ: **{money(selected_invoice['service_charge'])}**")
        st.write(f"VAT: **{money(selected_invoice['vat'])}**")
        st.subheader(f"Tổng thanh toán: {money(selected_invoice['total'])}")
        st.download_button(
            "⬇️ Tải chi tiết hóa đơn CSV",
            data=pd.DataFrame([dict(x) for x in items]).to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{selected_code or 'hoa_don'}.csv",
            mime="text/csv",
        )

# ---------------------------------------------------------
# 4. DOANH THU
# ---------------------------------------------------------
elif page == "📊 Doanh thu":
    st.subheader("📊 BÁO CÁO DOANH THU")
    d1, d2 = st.columns(2)
    date_from = d1.date_input("Từ ngày", value=date.today() - timedelta(days=6))
    date_to = d2.date_input("Đến ngày", value=date.today())
    if date_from > date_to:
        st.error("Ngày bắt đầu không được sau ngày kết thúc.")
    else:
        start = datetime.combine(date_from, time.min).strftime("%Y-%m-%d %H:%M:%S")
        end = datetime.combine(date_to, time.max).strftime("%Y-%m-%d %H:%M:%S")
        with connect_db() as conn:
            rows = conn.execute(
                "SELECT * FROM invoices WHERE created_at BETWEEN ? AND ? ORDER BY created_at DESC",
                (start, end),
            ).fetchall()
        if not rows:
            st.info("Không có hóa đơn trong khoảng thời gian đã chọn.")
        else:
            df = pd.DataFrame([dict(x) for x in rows])
            revenue = float(df["total"].fillna(0).sum())
            count = len(df)
            avg = revenue / count if count else 0
            m1, m2, m3 = st.columns(3)
            m1.metric("💰 Tổng doanh thu", money(revenue))
            m2.metric("🧾 Số hóa đơn", count)
            m3.metric("📈 Trung bình / hóa đơn", money(avg))
            st.divider()
            df["Ngày"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d")
            daily = df.groupby("Ngày", as_index=False)["total"].sum()
            daily["Doanh thu"] = daily["total"].apply(money)
            st.dataframe(daily[["Ngày", "Doanh thu"]], use_container_width=True, hide_index=True)
            st.bar_chart(daily.set_index("Ngày")["total"])
            st.download_button(
                "⬇️ Xuất báo cáo doanh thu CSV",
                data=df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"doanh_thu_{date_from}_{date_to}.csv",
                mime="text/csv",
            )

# ---------------------------------------------------------
# 5. TRỢ LÝ AI
# ---------------------------------------------------------
elif page == "🤖 Trợ lý AI Tư vấn":
    st.subheader("🤖 TRỢ LÝ AI TƯ VẤN MÓN ĂN & QUẢN LÝ")
    st.caption("Gợi ý thực đơn theo số người, khẩu vị và ngân sách, chỉ dùng món đang bán.")

    with st.expander("⚡ GỢI Ý NHANH THEO YÊU CẦU", expanded=True):
        p1, p2 = st.columns([1, 3])
        people = p1.number_input("Số khách", min_value=1, max_value=100, value=4, step=1)
        preferences = p2.text_input(
            "Sở thích / ghi chú",
            placeholder="Ví dụ: có trẻ em, không ăn cay, thích lẩu, ngân sách 800.000đ",
        )
        quick = st.button("💡 Gợi ý combo ngay", type="primary", use_container_width=True)

    model = st.selectbox("Mô hình AI", FREE_MODELS)
    left, right = st.columns([3, 1])
    if left.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.ai_messages = [{
            "role": "assistant",
            "content": "Đã xóa lịch sử trò chuyện. Bạn muốn tư vấn thực đơn nào? 🍀",
        }]
        st.rerun()

    for message in st.session_state.ai_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = ""
    if quick:
        prompt = (
            f"Tư vấn combo cho {people} người. Yêu cầu: "
            f"{preferences.strip() or 'ăn đa dạng, vừa đủ no'}."
        )
    chat_text = st.chat_input("Nhập câu hỏi về món ăn hoặc thực đơn...")
    if chat_text:
        prompt = chat_text.strip()

    if prompt:
        st.session_state.ai_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        system_message = {
            "role": "system",
            "content": (
                "Bạn là nhân viên tư vấn ẩm thực thân thiện của Nhà Hàng Cỏ Bốn Lá. "
                "Chỉ đề xuất món có trong menu được cung cấp. Không bịa món hoặc giá. "
                "Hỏi lại nếu thiếu thông tin quan trọng. Với combo, ghi món, số lượng, "
                "đơn giá, thành tiền và tổng dự kiến; cân đối khẩu phần, không cam kết chính xác "
                "khẩu phần nếu chưa có định lượng. Nếu ngân sách không đủ, nêu rõ và đề xuất "
                "phương án phù hợp hơn.\n\n" + get_restaurant_summary()
            ),
        }
        # Gửi một lượng lịch sử gần nhất để tránh payload quá lớn.
        messages = [system_message] + st.session_state.ai_messages[-12:]
        api_key = get_api_key()
        with st.chat_message("assistant"):
            with st.spinner("Trợ lý AI đang suy nghĩ..."):
                answer = call_openrouter(api_key, messages, model)
                st.markdown(answer)
        st.session_state.ai_messages.append({"role": "assistant", "content": answer})
