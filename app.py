import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st

# =========================================================
# NHÀ HÀNG CỎ BỐN LÁ - APP GỌI MÓN & HÓA ĐƠN
# =========================================================

st.set_page_config(
    page_title="Nhà Hàng Cỏ BỐN LÁ",
    page_icon="🍀",
    layout="wide"
)

DB = "co_bon_la.db"
LOGO = "Logo1.JPG"

# =========================================================
# DATABASE & MIGRATION AUTOMATION
# =========================================================

def connect_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect_db()
    cur = conn.cursor()

    # Bảng danh mục món ăn
    cur.execute("""
        CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            unit TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
    """)

    # Bảng thông tin hóa đơn
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_code TEXT UNIQUE,
            table_number TEXT,
            employee TEXT,
            customer TEXT,
            subtotal REAL,
            discount REAL,
            service_charge REAL,
            vat REAL,
            total REAL,
            payment_method TEXT,
            received REAL,
            change_money REAL,
            created_at TEXT
        )
    """)

    # Bảng chi tiết món ăn trong hóa đơn
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            menu_id INTEGER,
            item_name TEXT,
            quantity INTEGER,
            unit_price REAL,
            amount REAL
        )
    """)

    # --- 1. TỰ ĐỘNG MIGRATION CHO BẢNG INVOICES (DB CŨ) ---
    cur.execute("PRAGMA table_info(invoices)")
    inv_cols = [col[1] for col in cur.fetchall()]
    
    req_inv_cols = {
        "customer": "TEXT",
        "subtotal": "REAL",
        "discount": "REAL",
        "service_charge": "REAL",
        "vat": "REAL",
        "total": "REAL",
        "payment_method": "TEXT",
        "received": "REAL",
        "change_money": "REAL"
    }

    for col, col_type in req_inv_cols.items():
        if col not in inv_cols:
            cur.execute(f"ALTER TABLE invoices ADD COLUMN {col} {col_type}")

    # --- 2. TỰ ĐỘNG MIGRATION CHO BẢNG INVOICE_ITEMS (DB CŨ) ---
    cur.execute("PRAGMA table_info(invoice_items)")
    item_cols = [col[1] for col in cur.fetchall()]

    req_item_cols = {
        "invoice_id": "INTEGER",
        "menu_id": "INTEGER",
        "item_name": "TEXT",
        "quantity": "INTEGER",
        "unit_price": "REAL",
        "amount": "REAL"
    }

    for col, col_type in req_item_cols.items():
        if col not in item_cols:
            cur.execute(f"ALTER TABLE invoice_items ADD COLUMN {col} {col_type}")

    # Khởi tạo dữ liệu mẫu nếu bảng menu còn trống
    cur.execute("SELECT COUNT(*) FROM menu")
    if cur.fetchone()[0] == 0:
        sample = [
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

        cur.executemany(
            "INSERT INTO menu(name, category, price, unit) VALUES (?, ?, ?, ?)",
            sample
        )

    conn.commit()
    conn.close()


def money(number):
    return f"{number:,.0f} đ".replace(",", ".")


def get_menu():
    conn = connect_db()
    rows = conn.execute("""
        SELECT * FROM menu
        WHERE active = 1
        ORDER BY category, name
    """).fetchall()
    conn.close()
    return [dict(x) for x in rows]


def invoice_code():
    return "CBL-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:20]


def save_invoice(info, cart):
    conn = connect_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO invoices (
            invoice_code, table_number, employee, customer,
            subtotal, discount, service_charge, vat, total,
            payment_method, received, change_money, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        info["invoice_code"],
        info["table"],
        info["employee"],
        info["customer"],
        info["subtotal"],
        info["discount"],
        info["service"],
        info["vat"],
        info["total"],
        info["payment"],
        info["received"],
        info["change"],
        info["created_at"]
    ))

    invoice_id = cur.lastrowid

    for item in cart:
        cur.execute("""
            INSERT INTO invoice_items (
                invoice_id, menu_id, item_name,
                quantity, unit_price, amount
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            invoice_id,
            item["id"],
            item["name"],
            item["quantity"],
            item["price"],
            item["amount"]
        ))

    conn.commit()
    conn.close()


init_db()

# =========================================================
# SESSION STATE
# =========================================================

if "cart" not in st.session_state:
    st.session_state.cart = []

if "last_invoice" not in st.session_state:
    st.session_state.last_invoice = None


def add_item(item, quantity):
    for x in st.session_state.cart:
        if x["id"] == item["id"]:
            x["quantity"] += quantity
            x["amount"] = x["quantity"] * x["price"]
            return

    st.session_state.cart.append({
        "id": item["id"],
        "name": item["name"],
        "price": item["price"],
        "unit": item["unit"],
        "quantity": quantity,
        "amount": item["price"] * quantity
    })


# =========================================================
# GIAO DIỆN HỆ THỐNG
# =========================================================

st.markdown("""
<style>
.title {
    font-size: 34px;
    font-weight: 800;
    color: #166534;
}
.menu-box {
    border: 1px solid #d1d5db;
    border-radius: 12px;
    padding: 12px;
    background: #ffffff;
}
.total-box {
    padding: 18px;
    border-radius: 14px;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
}
</style>
""", unsafe_allow_html=True)

# HEADER
h1, h2 = st.columns([1, 6])

with h1:
    if Path(LOGO).exists():
        st.image(LOGO, width=100)
    else:
        st.write("🍀")

with h2:
    st.markdown(
        '<div class="title">NHÀ HÀNG CỎ BỐN LÁ</div>',
        unsafe_allow_html=True
    )
    st.caption("Hệ thống gọi món và quản lý hóa đơn")

st.divider()

# =========================================================
# SIDEBAR NAVIGATION
# =========================================================

st.sidebar.title("🍀 CỎ BỐN LÁ")

page = st.sidebar.radio(
    "MENU HỆ THỐNG",
    [
        "🧾 Bán hàng",
        "🍽️ Quản lý món",
        "📜 Hóa đơn",
        "📊 Doanh thu"
    ]
)

# =========================================================
# 1. TRANG BÁN HÀNG
# =========================================================

if page == "🧾 Bán hàng":

    st.subheader("🧾 TẠO HÓA ĐƠN")

    c1, c2, c3 = st.columns(3)

    with c1:
        table = st.text_input("🪑 Bàn số", placeholder="Ví dụ: Bàn 05")

    with c2:
        employee = st.text_input(
            "👨‍💼 Nhân viên",
            placeholder="Nhập tên nhân viên"
        )

    with c3:
        customer = st.text_input(
            "👤 Tên khách hàng",
            placeholder="Không bắt buộc"
        )

    st.divider()

    st.markdown("### 🍽 MENU MÓN ĂN")

    menu = get_menu()

    if not menu:
        st.warning("Chưa có món ăn. Hãy vào Quản lý món để thêm món.")
    else:
        categories = ["Tất cả"] + sorted(
            list(set(item["category"] for item in menu))
        )

        category = st.selectbox(
            "Chọn nhóm món",
            categories
        )

        if category == "Tất cả":
            menu_show = menu
        else:
            menu_show = [
                item for item in menu
                if item["category"] == category
            ]

        menu_names = [
            f'{item["name"]} — {money(item["price"])} / {item["unit"]}'
            for item in menu_show
        ]

        selected_text = st.selectbox(
            "🍴 Chọn món",
            menu_names,
            index=0
        )

        selected_index = menu_names.index(selected_text)
        selected_item = menu_show[selected_index]

        c1, c2, c3 = st.columns([3, 1, 2])

        with c1:
            st.markdown(
                f"""
                <div class="menu-box">
                <b>{selected_item["name"]}</b><br>
                Danh mục: {selected_item["category"]}<br>
                Giá: <b>{money(selected_item["price"])}</b> / {selected_item["unit"]}
                </div>
                """,
                unsafe_allow_html=True
            )

        with c2:
            quantity = st.number_input(
                "Số lượng",
                min_value=1,
                value=1,
                step=1
            )

        with c3:
            st.write("")
            st.write("")
            if st.button(
                "➕ THÊM MÓN VÀO HÓA ĐƠN",
                type="primary",
                width="stretch"
            ):
                add_item(selected_item, quantity)
                st.success(
                    f'Đã thêm {quantity} {selected_item["unit"]}: '
                    f'{selected_item["name"]}'
                )

    st.divider()

    st.markdown("### 🛒 MÓN ĐÃ CHỌN")

    if not st.session_state.cart:
        st.info(
            "Chưa có món. Nhân viên chọn món trong MENU phía trên "
            "để thêm vào hóa đơn."
        )

    else:
        for i, item in enumerate(st.session_state.cart):

            c1, c2, c3, c4, c5 = st.columns([3, 1, 1.5, 1.5, 0.6])

            with c1:
                st.write(f"**{item['name']}**")

            with c2:
                st.write(f"{item['quantity']} {item['unit']}")

            with c3:
                st.write(money(item["price"]))

            with c4:
                st.write(f"**{money(item['amount'])}**")

            with c5:
                if st.button("🗑️", key=f"delete_{i}"):
                    st.session_state.cart.pop(i)
                    st.rerun()

        st.divider()

        subtotal = sum(item["amount"] for item in st.session_state.cart)

        c1, c2 = st.columns(2)

        with c1:
            discount = st.number_input(
                "🏷️ Giảm giá (VNĐ)",
                min_value=0.0,
                value=0.0,
                step=1000.0
            )

            service_percent = st.number_input(
                "🍽️ Phí phục vụ (%)",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=1.0
            )

            vat_percent = st.number_input(
                "🧾 VAT (%)",
                min_value=0.0,
                max_value=100.0,
                value=0.0,
                step=1.0
            )

        service = max(subtotal - discount, 0) * service_percent / 100
        vat = max(subtotal - discount + service, 0) * vat_percent / 100
        total = max(subtotal - discount + service + vat, 0)

        with c2:
            payment = st.selectbox(
                "💳 Phương thức thanh toán",
                ["Tiền mặt", "Chuyển khoản", "Thẻ"]
            )

            if payment == "Tiền mặt":
                received = st.number_input(
                    "💵 Tiền khách đưa",
                    min_value=0.0,
                    value=float(total),
                    step=1000.0
                )
            else:
                received = total
                st.write(f"Khách thanh toán: **{money(total)}**")

            change = max(received - total, 0)

        st.markdown(
            f"""
            <div class="total-box">
                Tiền hàng: <b>{money(subtotal)}</b><br>
                Giảm giá: <b>- {money(discount)}</b><br>
                Phí phục vụ: <b>{money(service)}</b><br>
                VAT: <b>{money(vat)}</b><br>
                <hr>
                <b>TỔNG THANH TOÁN</b>
                <div style="font-size:30px;color:#166534;font-weight:800">
                    {money(total)}
                </div>
                Tiền thừa: <b>{money(change)}</b>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.write("")

        b1, b2 = st.columns([3, 1])

        with b1:
            if st.button(
                "💾 THANH TOÁN & LƯU HÓA ĐƠN",
                type="primary",
                width="stretch"
            ):

                if not table.strip():
                    st.error("Vui lòng nhập số bàn.")
                elif not employee.strip():
                    st.error("Vui lòng nhập tên nhân viên.")
                elif payment == "Tiền mặt" and received < total:
                    st.error("Tiền khách đưa chưa đủ.")
                else:
                    code = invoice_code()
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    info = {
                        "invoice_code": code,
                        "table": table,
                        "employee": employee,
                        "customer": customer,
                        "subtotal": subtotal,
                        "discount": discount,
                        "service": service,
                        "vat": vat,
                        "total": total,
                        "payment": payment,
                        "received": received,
                        "change": change,
                        "created_at": now
                    }

                    save_invoice(
                        info,
                        st.session_state.cart
                    )

                    st.session_state.last_invoice = info
                    st.session_state.cart = []

                    st.success(
                        f"✅ Lưu hóa đơn thành công: {code} | "
                        f"Tổng: {money(total)}"
                    )

                    st.balloons()

        with b2:
            if st.button("🗑️ XÓA BILL", width="stretch"):
                st.session_state.cart = []
                st.rerun()

# =========================================================
# 2. TRANG QUẢN LÝ MÓN
# =========================================================

elif page == "🍽️ Quản lý món":

    st.subheader("🍽️ QUẢN LÝ MENU MÓN ĂN")

    tab1, tab2 = st.tabs(["➕ Thêm món", "📋 Danh sách món"])

    with tab1:
        with st.form("add_food"):
            name = st.text_input("Tên món")
            category = st.selectbox(
                "Danh mục",
                [
                    "Khai vị",
                    "Món chính",
                    "Món phụ",
                    "Nước uống",
                    "Tráng miệng",
                    "Khác"
                ]
            )
            price = st.number_input(
                "Giá bán (VNĐ)",
                min_value=0.0,
                step=1000.0
            )
            unit = st.selectbox(
                "Đơn vị",
                ["Phần", "Nồi", "Đĩa", "Ly", "Lon", "Chai", "Cái"]
            )

            if st.form_submit_button("➕ THÊM MÓN", type="primary"):
                if not name.strip():
                    st.error("Vui lòng nhập tên món.")
                elif price <= 0:
                    st.error("Vui lòng nhập giá bán.")
                else:
                    conn = connect_db()
                    conn.execute(
                        """
                        INSERT INTO menu(name, category, price, unit, active)
                        VALUES (?, ?, ?, ?, 1)
                        """,
                        (name.strip(), category, price, unit)
                    )
                    conn.commit()
                    conn.close()

                    st.success(f"Đã thêm món: {name}")
                    st.rerun()

    with tab2:
        conn = connect_db()
        foods = conn.execute(
            "SELECT * FROM menu ORDER BY category, name"
        ).fetchall()
        conn.close()

        if foods:
            df = pd.DataFrame([dict(x) for x in foods])
            df["Giá"] = df["price"].apply(money)
            df["Trạng thái"] = df["active"].map(
                {1: "Đang bán", 0: "Ngừng bán"}
            )

            st.dataframe(
                df[
                    [
                        "id",
                        "name",
                        "category",
                        "Giá",
                        "unit",
                        "Trạng thái"
                    ]
                ].rename(
                    columns={
                        "id": "ID",
                        "name": "Tên món",
                        "category": "Danh mục",
                        "unit": "Đơn vị"
                    }
                ),
                width="stretch",
                hide_index=True
            )

            food_ids = [x["id"] for x in foods]

            selected_id = st.selectbox(
                "Chọn món cần chỉnh sửa",
                food_ids,
                format_func=lambda x: next(
                    y["name"] for y in foods if y["id"] == x
                )
            )

            selected = next(x for x in foods if x["id"] == selected_id)

            new_name = st.text_input("Tên món", value=selected["name"])
            new_price = st.number_input(
                "Giá bán",
                min_value=0.0,
                value=float(selected["price"]),
                step=1000.0
            )

            b1, b2 = st.columns(2)

            with b1:
                if st.button(
                    "💾 LƯU THAY ĐỔI",
                    type="primary",
                    width="stretch"
                ):
                    conn = connect_db()
                    conn.execute(
                        """
                        UPDATE menu
                        SET name = ?, price = ?
                        WHERE id = ?
                        """,
                        (new_name, new_price, selected_id)
                    )
                    conn.commit()
                    conn.close()

                    st.success("Đã cập nhật món.")
                    st.rerun()

            with b2:
                text = (
                    "⛔ NGỪNG BÁN" if selected["active"] else "✅ BÁN LẠI"
                )

                if st.button(text, width="stretch"):
                    new_status = 0 if selected["active"] else 1
                    conn = connect_db()
                    conn.execute(
                        """
                        UPDATE menu
                        SET active = ?
                        WHERE id = ?
                        """,
                        (new_status, selected_id)
                    )
                    conn.commit()
                    conn.close()
                    st.rerun()

# =========================================================
# 3. TRANG LỊCH SỬ HÓA ĐƠN
# =========================================================

elif page == "📜 Hóa đơn":

    st.subheader("📜 LỊCH SỬ HÓA ĐƠN")

    search = st.text_input(
        "🔎 Tìm hóa đơn",
        placeholder="Nhập mã hóa đơn, bàn hoặc nhân viên"
    )

    conn = connect_db()

    if search.strip():
        invoices = conn.execute(
            """
            SELECT *
            FROM invoices
            WHERE invoice_code LIKE ?
               OR table_number LIKE ?
               OR employee LIKE ?
            ORDER BY id DESC
            """,
            (f"%{search}%", f"%{search}%", f"%{search}%")
        ).fetchall()
    else:
        invoices = conn.execute(
            """
            SELECT *
            FROM invoices
            ORDER BY id DESC
            """
        ).fetchall()

    conn.close()

    if not invoices:
        st.info("Chưa có hóa đơn.")
    else:
        df = pd.DataFrame([dict(x) for x in invoices])
        df["Tổng tiền"] = df["total"].apply(money)

        st.dataframe(
            df[
                [
                    "invoice_code",
                    "table_number",
                    "employee",
                    "payment_method",
                    "Tổng tiền",
                    "created_at"
                ]
            ].rename(
                columns={
                    "invoice_code": "Mã HĐ",
                    "table_number": "Bàn",
                    "employee": "Nhân viên",
                    "payment_method": "Thanh toán",
                    "created_at": "Thời gian"
                }
            ),
            width="stretch",
            hide_index=True
        )

# =========================================================
# 4. TRANG BÁO CÁO DOANH THU
# =========================================================

elif page == "📊 Doanh thu":

    st.subheader("📊 DOANH THU")

    c1, c2 = st.columns(2)

    with c1:
        date_from = st.date_input("Từ ngày", datetime.now().date())

    with c2:
        date_to = st.date_input("Đến ngày", datetime.now().date())

    start = str(date_from) + " 00:00:00"
    end = str(date_to) + " 23:59:59"

    conn = connect_db()

    invoices = conn.execute(
        """
        SELECT *
        FROM invoices
        WHERE created_at BETWEEN ? AND ?
        ORDER BY created_at DESC
        """,
        (start, end)
    ).fetchall()

    conn.close()

    if not invoices:
        st.info("Không có dữ liệu trong khoảng thời gian này.")
    else:
        df = pd.DataFrame([dict(x) for x in invoices])

        total_revenue = df["total"].sum()
        count = len(df)
        average = total_revenue / count

        c1, c2, c3 = st.columns(3)

        c1.metric("💰 Tổng doanh thu", money(total_revenue))
        c2.metric("🧾 Số hóa đơn", count)
        c3.metric("📈 Trung bình / hóa đơn", money(average))

        st.divider()

        df["Ngày"] = pd.to_datetime(df["created_at"]).dt.date

        daily = (
            df.groupby("Ngày")["total"]
            .sum()
            .reset_index()
        )

        daily["Doanh thu"] = daily["total"].apply(money)

        st.dataframe(
            daily[["Ngày", "Doanh thu"]],
            width="stretch",
            hide_index=True
        )
