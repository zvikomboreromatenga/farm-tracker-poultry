import streamlit as st
import datetime
from collections import defaultdict
import json
import io
import csv
import zipfile
import os
import shutil

# Initialize session state
if 'egg_inventory' not in st.session_state:
    # Format: {incubation_date: number_of_eggs}
    st.session_state.egg_inventory = defaultdict(int)
if 'hatchery' not in st.session_state:
    # Format: {date: {"location": ..., "chicks": ...}}
    st.session_state.hatchery = []
if 'chicks_orders' not in st.session_state:
    # List of dicts: {name, order_count, order_date, pickup_date, picked_up}
    st.session_state.chicks_orders = []
if 'chicks_inventory' not in st.session_state:
    st.session_state.chicks_inventory = 0
if 'sales' not in st.session_state:
    # Each sale: {type: "chick/cock/pol", name, count, date}
    st.session_state.sales = []
if 'processed_hatch_dates' not in st.session_state:
    # Track incubation dates that have already been processed into chicks
    st.session_state.processed_hatch_dates = []

# Utility: Calculate available chicks and forecast pickup dates
def get_total_eggs(current_date=None):
    if current_date is None:
        current_date = datetime.date.today()
    eggs = sum(val for incubation_date, val in st.session_state.egg_inventory.items() if incubation_date <= current_date)
    return eggs

def forecast_pickup_dates():
    # Orders sorted by date
    all_orders = sorted(st.session_state.chicks_orders, key=lambda x: x['order_date'])
    # Consider existing eggs, hatch rate, and 3-week incubation
    agg_eggs = 0
    plan_dates = []
    today = datetime.date.today()
    # Estimate available batches over next few weeks
    eggs_by_hatch_day = {}
    for incubation_date, egg_count in st.session_state.egg_inventory.items():
        hatch_day = incubation_date + datetime.timedelta(weeks=3)
        if hatch_day >= today:
            hatched_chicks = int(egg_count * 0.85)
            eggs_by_hatch_day[hatch_day] = eggs_by_hatch_day.get(hatch_day, 0) + hatched_chicks
    # Assign earliest available batch to each order
    egg_stock = eggs_by_hatch_day.copy()
    for order in all_orders:
        for hatch_day in sorted(egg_stock.keys()):
            if egg_stock[hatch_day] >= order['order_count']:
                plan_dates.append(hatch_day)
                egg_stock[hatch_day] -= order['order_count']
                order['pickup_date'] = hatch_day
                break
        else:
            plan_dates.append(None)  # Not enough supply
            order['pickup_date'] = None
    return all_orders


def process_hatches():
    """Convert incubating eggs to chicks once their hatch day has arrived.
    This moves hatched eggs out of `egg_inventory`, increases `chicks_inventory`,
    and logs an entry in `hatchery`. Processed incubation dates are tracked
    in `processed_hatch_dates` to avoid double counting across reruns.
    """
    today = datetime.date.today()
    # Collect incubation dates that need processing to avoid modifying dict while iterating
    to_process = []
    for incubation_date, egg_count in list(st.session_state.egg_inventory.items()):
        hatch_day = incubation_date + datetime.timedelta(weeks=3)
        key = incubation_date.isoformat() if hasattr(incubation_date, 'isoformat') else str(incubation_date)
        if hatch_day <= today and key not in st.session_state.processed_hatch_dates:
            hatched_chicks = int(egg_count * 0.85)
            to_process.append((incubation_date, hatch_day, hatched_chicks))

    for incubation_date, hatch_day, hatched_chicks in to_process:
        # Remove eggs that hatched
        if incubation_date in st.session_state.egg_inventory:
            del st.session_state.egg_inventory[incubation_date]
        # Add to chicks inventory and hatchery record
        st.session_state.chicks_inventory += hatched_chicks
        st.session_state.hatchery.append({"date": hatch_day, "location": "Auto Hatch", "chicks": hatched_chicks})
        st.session_state.processed_hatch_dates.append(incubation_date.isoformat())


# --- Persistence helpers: Streamlit Cloud/local file ---
DATA_PATH = ".streamlit/data.json"

def save_to_local(path=DATA_PATH):
    payload = {
        'egg_inventory': {str(k): v for k, v in st.session_state.egg_inventory.items()},
        'hatchery': st.session_state.hatchery,
        'chicks_orders': [
            {
                'name': o.get('name'),
                'order_count': o.get('order_count'),
                'order_date': str(o.get('order_date')) if o.get('order_date') else None,
                'pickup_date': str(o.get('pickup_date')) if o.get('pickup_date') else None,
                'picked_up': bool(o.get('picked_up'))
            } for o in st.session_state.chicks_orders
        ],
        'chicks_inventory': st.session_state.chicks_inventory,
        'sales': [
            {'type': s.get('type'), 'name': s.get('name'), 'count': s.get('count'), 'date': str(s.get('date')) if s.get('date') else None}
            for s in st.session_state.sales
        ],
        'processed_hatch_dates': st.session_state.processed_hatch_dates,
    }
    try:
        import os
        os.makedirs('.streamlit', exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"Error saving local data: {e}")
        return False


def load_from_local(path=DATA_PATH):
    try:
        import os
        if not os.path.exists(path):
            return False
        with open(path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        # egg_inventory
        st.session_state.egg_inventory = defaultdict(int)
        for k, v in payload.get('egg_inventory', {}).items():
            try:
                st.session_state.egg_inventory[datetime.datetime.strptime(k, "%Y-%m-%d").date()] = int(v)
            except Exception:
                pass
        # hatchery
        st.session_state.hatchery = payload.get('hatchery', [])
        # chicks_orders
        st.session_state.chicks_orders = []
        for o in payload.get('chicks_orders', []):
            order_date = datetime.datetime.strptime(o.get('order_date'), "%Y-%m-%d").date() if o.get('order_date') else None
            pickup_date = datetime.datetime.strptime(o.get('pickup_date'), "%Y-%m-%d").date() if o.get('pickup_date') else None
            st.session_state.chicks_orders.append({
                'name': o.get('name'), 'order_count': int(o.get('order_count', 0)), 'order_date': order_date, 'pickup_date': pickup_date, 'picked_up': bool(o.get('picked_up', False))
            })
        # chicks_inventory
        st.session_state.chicks_inventory = int(payload.get('chicks_inventory', 0))
        # sales
        st.session_state.sales = []
        for s in payload.get('sales', []):
            date = datetime.datetime.strptime(s.get('date'), "%Y-%m-%d").date() if s.get('date') else None
            st.session_state.sales.append({'type': s.get('type'), 'name': s.get('name'), 'count': int(s.get('count', 0)), 'date': date})
        st.session_state.processed_hatch_dates = payload.get('processed_hatch_dates', [])
        return True
    except Exception as e:
        st.error(f"Error loading local data: {e}")
        return False


def export_data_zip():
    """Export current session data as a ZIP archive containing CSVs.
    Returns bytes of the ZIP file.
    """
    mem = io.BytesIO()
    try:
        with zipfile.ZipFile(mem, mode='w', compression=zipfile.ZIP_DEFLATED) as z:
            # egg_inventory.csv
            si = io.StringIO()
            writer = csv.writer(si)
            writer.writerow(['date', 'eggs'])
            for k, v in st.session_state.egg_inventory.items():
                writer.writerow([str(k), v])
            z.writestr('egg_inventory.csv', si.getvalue())

            # hatchery.csv
            si = io.StringIO()
            writer = csv.writer(si)
            writer.writerow(['date', 'location', 'chicks'])
            for h in st.session_state.hatchery:
                writer.writerow([str(h.get('date')), h.get('location', ''), h.get('chicks', 0)])
            z.writestr('hatchery.csv', si.getvalue())

            # chicks_orders.csv
            si = io.StringIO()
            writer = csv.writer(si)
            writer.writerow(['name', 'order_count', 'order_date', 'pickup_date', 'picked_up'])
            for o in st.session_state.chicks_orders:
                writer.writerow([o.get('name',''), o.get('order_count',0), str(o.get('order_date') or ''), str(o.get('pickup_date') or ''), bool(o.get('picked_up', False))])
            z.writestr('chicks_orders.csv', si.getvalue())

            # sales.csv
            si = io.StringIO()
            writer = csv.writer(si)
            writer.writerow(['type', 'name', 'count', 'date'])
            for s in st.session_state.sales:
                writer.writerow([s.get('type',''), s.get('name',''), s.get('count',0), str(s.get('date') or '')])
            z.writestr('sales.csv', si.getvalue())

            # meta.json
            meta = {
                'chicks_inventory': st.session_state.chicks_inventory,
                'processed_hatch_dates': st.session_state.processed_hatch_dates,
                'exported_at': str(datetime.date.today())
            }
            z.writestr('meta.json', json.dumps(meta))

        mem.seek(0)
        return mem.read()
    except Exception as e:
        st.error(f"Error exporting data: {e}")
        return None


def _ensure_backups_dir():
    d = os.path.join('.streamlit', 'backups')
    os.makedirs(d, exist_ok=True)
    return d


def save_backup_zip():
    """Create a timestamped ZIP backup file under .streamlit/backups/ and return the path."""
    try:
        data = export_data_zip()
        if not data:
            return None
        d = _ensure_backups_dir()
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'farm_backup_{ts}.zip'
        path = os.path.join(d, filename)
        with open(path, 'wb') as f:
            f.write(data)
        # Rotate old backups, keep latest 10
        try:
            _rotate_backups(10)
        except Exception:
            pass
        return path
    except Exception as e:
        st.error(f"Error saving backup file: {e}")
        return None


def latest_backup_age_days():
    d = os.path.join('.streamlit', 'backups')
    if not os.path.exists(d):
        return None
    files = [f for f in os.listdir(d) if f.endswith('.zip')]
    if not files:
        return None
    paths = [os.path.join(d, f) for f in files]
    latest = max(paths, key=os.path.getmtime)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(latest))
    return (datetime.datetime.now() - mtime).total_seconds() / 86400.0


def _rotate_backups(max_keep=10):
    """Keep only the newest `max_keep` backup files in the backups directory."""
    d = os.path.join('.streamlit', 'backups')
    if not os.path.exists(d):
        return
    files = [f for f in os.listdir(d) if f.endswith('.zip')]
    if len(files) <= max_keep:
        return
    paths = [os.path.join(d, f) for f in files]
    paths_sorted = sorted(paths, key=os.path.getmtime, reverse=True)
    # Remove older ones beyond max_keep
    for old in paths_sorted[max_keep:]:
        try:
            os.remove(old)
        except Exception:
            pass


def list_backups():
    """Return a list of backups with metadata (name, path, size, mtime)."""
    d = os.path.join('.streamlit', 'backups')
    if not os.path.exists(d):
        return []
    files = [f for f in os.listdir(d) if f.endswith('.zip')]
    rows = []
    for f in sorted(files, reverse=True):
        p = os.path.join(d, f)
        try:
            size = os.path.getsize(p)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p))
            rows.append({
                'name': f,
                'path': p,
                'size': size,
                'mtime': mtime,
            })
        except Exception:
            continue
    return rows


def list_trash():
    d = os.path.join('.streamlit', 'backups', 'trash')
    if not os.path.exists(d):
        return []
    files = [f for f in os.listdir(d) if f.endswith('.zip')]
    rows = []
    for f in sorted(files, reverse=True):
        p = os.path.join(d, f)
        try:
            size = os.path.getsize(p)
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p))
            rows.append({
                'name': f,
                'path': p,
                'size': size,
                'mtime': mtime,
            })
        except Exception:
            continue
    return rows

# Ensure we process any hatches that have matured since last run
process_hatches()

# Auto-backup session defaults
if 'auto_backup_enabled' not in st.session_state:
    st.session_state.auto_backup_enabled = False
if 'auto_backup_days' not in st.session_state:
    st.session_state.auto_backup_days = 1

# Perform startup backup if enabled and due
try:
    if st.session_state.get('auto_backup_enabled'):
        age = latest_backup_age_days()
        if age is None or age >= float(st.session_state.get('auto_backup_days', 1)):
            p = save_backup_zip()
            if p:
                st.info(f"Startup backup created: {p}")
except Exception:
    pass

st.title('🐥 Chicken Farm Dashboard')

# Persistence UI (Streamlit Cloud / local file)
with st.expander("🔁 Persistence"):
    st.markdown("Persist app data to Streamlit Cloud's writable filesystem (local file). This keeps data between runs on the deployed app instance.")
    # Automatic backup controls
    if 'auto_backup_enabled' not in st.session_state:
        st.session_state.auto_backup_enabled = False
    if 'auto_backup_days' not in st.session_state:
        st.session_state.auto_backup_days = 1
    col0, _ = st.columns([2, 3])
    with col0:
        st.session_state.auto_backup_enabled = st.checkbox("Enable automatic backups", value=st.session_state.auto_backup_enabled)
        st.session_state.auto_backup_days = st.number_input("Backup interval (days)", min_value=1, step=1, value=st.session_state.auto_backup_days)
    col1, col2 = st.columns(2)
    if col1.button("Save to Streamlit storage"):
        ok = save_to_local()
        if ok:
            st.success("Saved data to .streamlit/data.json")
            if st.session_state.auto_backup_enabled:
                p = save_backup_zip()
                if p:
                    st.info(f"Backup saved to {p}")
    if col2.button("Load from Streamlit storage"):
        ok = load_from_local()
        if ok:
            st.success("Loaded data from .streamlit/data.json")
            # Optionally create backup after load if enabled
            if st.session_state.auto_backup_enabled:
                p = save_backup_zip()
                if p:
                    st.info(f"Backup saved to {p}")
    # Export backup as zip of CSVs
    zip_bytes = export_data_zip()
    if zip_bytes:
        st.download_button("Export backup (ZIP)", data=zip_bytes, file_name="farm_backup.zip", mime="application/zip")

    # List existing backups and allow deletion
    st.markdown("---")
    st.markdown("**Existing Backups**")
    backups = list_backups()
    if not backups:
        st.info("No backups found in .streamlit/backups/")
    else:
        # Display table
        table = []
        for b in backups:
            table.append({
                'File': b['name'],
                'Size (KB)': round(b['size'] / 1024, 1),
                'Modified': b['mtime'].strftime('%Y-%m-%d %H:%M:%S')
            })
        st.table(table)

        names = [b['name'] for b in backups]
        to_delete = st.multiselect("Select backups to delete", options=names)
        if st.button("Delete selected backups"):
            if not to_delete:
                st.warning("Select at least one backup to delete")
            else:
                # store pending deletion in session to ask for confirmation
                st.session_state['backups_pending_delete'] = to_delete

        # Confirmation step: show pending deletions and require explicit confirm
        pending = st.session_state.get('backups_pending_delete', [])
        if pending:
            st.warning(f"You are about to delete {len(pending)} backup(s): {', '.join(pending)}")
            c1, c2 = st.columns(2)
            if c1.button("Confirm delete (move to trash)"):
                trash_dir = os.path.join('.streamlit', 'backups', 'trash')
                os.makedirs(trash_dir, exist_ok=True)
                moved = []
                failed = []
                for b in backups:
                    if b['name'] in pending:
                        try:
                            dst = os.path.join(trash_dir, b['name'])
                            shutil.move(b['path'], dst)
                            moved.append(b['name'])
                        except Exception as e:
                            failed.append((b['name'], str(e)))
                # clear pending
                st.session_state['backups_pending_delete'] = []
                if moved:
                    st.success(f"Moved to trash: {', '.join(moved)}")
                for name, err in failed:
                    st.error(f"Failed to move {name}: {err}")
                st.experimental_rerun()
            if c2.button("Cancel"):
                st.session_state['backups_pending_delete'] = []
                st.info("Deletion canceled")

    # --- Trash management UI ---
    st.markdown("---")
    st.subheader("Trash")
    trash = list_trash()
    if trash:
        trash_table = []
        for t in trash:
            trash_table.append({
                'File': t['name'],
                'Size (KB)': round(t['size'] / 1024, 1),
                'Modified': t['mtime'].strftime('%Y-%m-%d %H:%M:%S')
            })
        st.table(trash_table)

        col_a, col_b, col_c = st.columns([2, 2, 2])
        with col_a:
            to_restore = st.multiselect("Select to restore", [t['name'] for t in trash], key='trash_restore_select')
            if st.button("Restore Selected"):
                restored = []
                for name in to_restore:
                    src = os.path.join('.streamlit', 'backups', 'trash', name)
                    dst = os.path.join('.streamlit', 'backups', name)
                    try:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.move(src, dst)
                        restored.append(name)
                    except Exception as e:
                        st.error(f"Failed to restore {name}: {e}")
                if restored:
                    st.success(f"Restored: {', '.join(restored)}")
                    st.experimental_rerun()
        with col_b:
            to_purge = st.multiselect("Select to permanently delete", [t['name'] for t in trash], key='trash_purge_select')
            if st.button("Permanently Delete Selected"):
                purged = []
                for name in to_purge:
                    p = os.path.join('.streamlit', 'backups', 'trash', name)
                    try:
                        os.remove(p)
                        purged.append(name)
                    except Exception as e:
                        st.error(f"Failed to delete {name}: {e}")
                if purged:
                    st.success(f"Permanently deleted: {', '.join(purged)}")
                    st.experimental_rerun()
        with col_c:
            if st.button("Empty Trash"):
                confirm = st.checkbox("I understand this will permanently delete all trashed backups")
                if confirm:
                    for t in trash:
                        try:
                            os.remove(t['path'])
                        except Exception:
                            pass
                    st.success("Trash emptied")
                    st.experimental_rerun()
    else:
        st.info("Trash is empty")

# --- PANEL 1: Chicks Orders ---
with st.expander("1️⃣ Chicks Orders Module"):
    st.subheader("Order Chicks")
    with st.form("Order chicks"):
        customer = st.text_input("Customer Name")
        num_chicks = st.number_input("No. of chicks", min_value=1, step=1, value=1)
        order_date = st.date_input("Order date", value=datetime.date.today())
        submit = st.form_submit_button("Place Order")
    if submit and customer:
        st.session_state.chicks_orders.append(
            {"name": customer, "order_count": int(num_chicks), "order_date": order_date, "pickup_date": None, "picked_up": False}
        )
        st.success("Order placed!")

    # Ensure each order has an assigned pickup_date where possible
    forecasted_orders = forecast_pickup_dates()
    st.markdown("#### Order List & Pickup Forecast")
    st.dataframe([{
        "Customer": order['name'],
        "Order Qty": order['order_count'],
        "Order Date": order['order_date'],
        "Pickup Date": order['pickup_date'],
        "Picked Up": "Yes" if order['picked_up'] else "No"
    } for order in forecasted_orders])

    # Inventory/forecast summary
    total_eggs = sum(st.session_state.egg_inventory.values())
    eggs_by_hatch = sum(egg_count * 0.85 for incubation_date, egg_count in st.session_state.egg_inventory.items())
    st.info(f"Total eggs in inventory: {total_eggs}, Forecasted chicks available (85% rate): {int(eggs_by_hatch)}")

    # --- New: Forecast availability by date ---
    st.markdown("#### Forecasted Chicks Availability by Date")
    col1, col2 = st.columns(2)
    today = datetime.date.today()
    start_date = col1.date_input("Forecast start date", value=today)
    end_date = col2.date_input("Forecast end date", value=today + datetime.timedelta(weeks=8))
    if start_date > end_date:
        st.error("Start date must be on or before end date")
    else:
        # Build hatched chicks by hatch date (incubation_date + 3 weeks)
        eggs_by_hatch_day = {}
        for incubation_date, egg_count in st.session_state.egg_inventory.items():
            hatch_day = incubation_date + datetime.timedelta(weeks=3)
            hatched_chicks = int(egg_count * 0.85)
            eggs_by_hatch_day[hatch_day] = eggs_by_hatch_day.get(hatch_day, 0) + hatched_chicks

        # Build allocated chicks per date from forecasted orders
        allocated_by_date = {}
        for ord in forecasted_orders:
            pd = ord.get('pickup_date')
            if pd is not None:
                allocated_by_date[pd] = allocated_by_date.get(pd, 0) + ord.get('order_count', 0)

        # Compose rows for each date in the requested range and compute cumulative/rolling availability
        rows = []
        cur = start_date
        cum_hatched = 0
        cum_alloc = 0
        while cur <= end_date:
            hatched = eggs_by_hatch_day.get(cur, 0)
            allocated = allocated_by_date.get(cur, 0)
            cum_hatched += hatched
            cum_alloc += allocated
            daily_available = max(0, hatched - allocated)
            rolling_available = max(0, cum_hatched - cum_alloc)
            rows.append({
                "Date": cur,
                "Hatched (est)": hatched,
                "Allocated to Orders": allocated,
                "Daily Available": daily_available,
                "Cumulative Hatched": cum_hatched,
                "Cumulative Allocated": cum_alloc,
                "Rolling Available": rolling_available,
            })
            cur += datetime.timedelta(days=1)

        st.dataframe(rows)

    # Summary totals and charts for Orders module
    st.markdown("##### Orders Summary & Chart")
    total_orders = len(st.session_state.chicks_orders)
    total_ordered_chicks = sum(o['order_count'] for o in st.session_state.chicks_orders)
    pending = sum(1 for o in st.session_state.chicks_orders if not o.get('picked_up'))
    st.write(f"Total orders: {total_orders} — Total chicks ordered: {total_ordered_chicks} — Pending orders: {pending}")

    # Orders per order_date chart (simple list + table for labels)
    orders_by_date = {}
    for o in st.session_state.chicks_orders:
        d = o.get('order_date')
        if d is None:
            continue
        orders_by_date[d] = orders_by_date.get(d, 0) + o.get('order_count', 0)
    if orders_by_date:
        dates = sorted(orders_by_date.keys())
        counts = [orders_by_date[d] for d in dates]
        st.bar_chart({"Ordered chicks": counts})
        st.table([{"Date": d, "Ordered": orders_by_date[d]} for d in dates])


# --- PANEL 2: Incoming Eggs ---
with st.expander("2️⃣ Egg Arrivals Module"):
    st.subheader("Record New Egg Arrivals")
    with st.form("log_egg_arrival"):
        arrival_date = st.date_input("Arrival Date", key='egg')
        source = st.selectbox("Egg Source", ["Contract Farmer", "Own Farm"])
        loc_or_customer = st.text_input("Farmer Name" if source=="Contract Farmer" else "Farm Location")
        num_eggs = st.number_input("Number of Eggs", min_value=1, step=1, value=10)
        submit_eggs = st.form_submit_button("Log Egg Arrival")
    if submit_eggs:
        st.session_state.egg_inventory[arrival_date] += int(num_eggs)
        st.success(f"Added {num_eggs} eggs from {loc_or_customer} on {arrival_date}")
        # Process any hatches that may now be ready (and refresh the app
        # so dependent modules recalculate with the new state)
        process_hatches()
        st.rerun()

    st.markdown("#### Egg Inventory (by Incubation Date)")
    eggs_df = [{"Date": str(date), "Eggs": count} for date, count in st.session_state.egg_inventory.items()]
    st.dataframe(eggs_df)
    st.info(f"Total eggs in incubators: {sum(st.session_state.egg_inventory.values())}")

    # Summary totals and chart for Egg Arrivals
    st.markdown("##### Eggs Summary & Chart")
    total_incubating = sum(st.session_state.egg_inventory.values())
    st.write(f"Total eggs incubating: {total_incubating}")
    if eggs_df:
        # show eggs by incubation date
        eggs_by_date = {datetime.datetime.strptime(r["Date"], "%Y-%m-%d").date(): r["Eggs"] for r in eggs_df}
        dates = sorted(eggs_by_date.keys())
        counts = [eggs_by_date[d] for d in dates]
        st.bar_chart({"Eggs (by incubation date)": counts})
        st.table([{"Date": d, "Eggs": eggs_by_date[d]} for d in dates])

# --- PANEL 3: Chicks Collection ---
with st.expander("3️⃣ Chicks Collection Module"):
    st.subheader("Customer Pickup")
    eligible_pickups = [
        order for order in forecasted_orders
        if order['pickup_date'] is not None and not order['picked_up'] and order['pickup_date'] <= datetime.date.today()
    ]
    pickup_options = [f"{order['name']} ({order['order_count']} chicks, {order['pickup_date']})"
                      for order in eligible_pickups]
    if pickup_options:
        pickup_idx = st.selectbox("Select customer for pickup", list(range(len(pickup_options))),
                                  format_func=lambda i: pickup_options[i])
        if st.button("Mark as Collected"):
            order = eligible_pickups[pickup_idx]
            order['picked_up'] = True
            st.session_state.chicks_inventory = max(0, st.session_state.chicks_inventory - order['order_count'])
            st.success(f"{order['name']} picked up {order['order_count']} chicks")

    # Chicks inventory is maintained by hatch processing and hatchery records
    st.markdown(f"**Chicks Inventory (as of today): {st.session_state.chicks_inventory}**")
    st.dataframe([{
        "Customer": order['name'],
        "Order Qty": order['order_count'],
        "Pickup Date": order['pickup_date'],
        "Picked Up": "Yes" if order['picked_up'] else "No"
    } for order in st.session_state.chicks_orders])

    # Summary totals and charts for Collection module
    st.markdown("##### Collection Summary & Chart")
    total_picked = sum(o['order_count'] for o in st.session_state.chicks_orders if o.get('picked_up'))
    total_pending_chicks = sum(o['order_count'] for o in st.session_state.chicks_orders if not o.get('picked_up') and o.get('pickup_date') is not None)
    st.write(f"Chicks inventory: {st.session_state.chicks_inventory} — Picked up total: {total_picked} — Pending chicks with pickup date: {total_pending_chicks}")
    # Pickups per pickup_date
    pickups_by_date = {}
    for o in st.session_state.chicks_orders:
        if o.get('picked_up') and o.get('pickup_date') is not None:
            d = o['pickup_date']
            pickups_by_date[d] = pickups_by_date.get(d, 0) + o.get('order_count', 0)
    if pickups_by_date:
        dates = sorted(pickups_by_date.keys())
        counts = [pickups_by_date[d] for d in dates]
        st.line_chart({"Picked up chicks": counts})
        st.table([{"Date": d, "Picked Up": pickups_by_date[d]} for d in dates])

# --- PANEL 4: Hatchery ---
with st.expander("4️⃣ Hatchery Module"):
    st.subheader("Hatchery Operations")
    with st.form("record_hatching"):
        hatch_date = st.date_input("Hatch Date", key='hatch')
        location = st.text_input("Location")
        new_chicks = st.number_input("No. of newly hatched chicks", min_value=0, step=1, value=0)
        save_hatch = st.form_submit_button("Add Hatch Data")
    if save_hatch and new_chicks > 0:
        st.session_state.hatchery.append({"date": hatch_date, "location": location, "chicks": int(new_chicks)})
        st.session_state.chicks_inventory += int(new_chicks)
        st.success(f"Added {new_chicks} chicks from {location} on {hatch_date}")

    st.markdown("#### Hatchery Record")
    st.dataframe(st.session_state.hatchery)

    # Summary totals and chart for Hatchery
    st.markdown("##### Hatchery Summary & Chart")
    total_hatched = sum(h.get('chicks', 0) for h in st.session_state.hatchery)
    st.write(f"Total hatched (recorded): {total_hatched}")
    if st.session_state.hatchery:
        hatch_by_date = {}
        for h in st.session_state.hatchery:
            d = h.get('date')
            hatch_by_date[d] = hatch_by_date.get(d, 0) + h.get('chicks', 0)
        dates = sorted(hatch_by_date.keys())
        counts = [hatch_by_date[d] for d in dates]
        st.bar_chart({"Hatched chicks": counts})
        st.table([{"Date": d, "Hatched": hatch_by_date[d]} for d in dates])

# --- PANEL 5: Sales ---
with st.expander("5️⃣ Sales Module"):
    st.subheader("Sales Entry")
    with st.form("record_sale"):
        sale_type = st.selectbox("Sale Type", ["Chick", "Cock", "Point of Lay"])
        sale_customer = st.text_input("Customer Name (Sale)")
        sale_qty = st.number_input("Sale Quantity", min_value=1, step=1, value=1)
        sale_dt = st.date_input("Sale Date", key='sale')
        submit_sale = st.form_submit_button("Log Sale")
    if submit_sale and sale_customer:
        st.session_state.sales.append({
            "type": sale_type, "name": sale_customer,
            "count": int(sale_qty), 
            "date": sale_dt
        })
        # Subtract from inventory if chicks are sold
        if sale_type == "Chick":
            st.session_state.chicks_inventory = max(0, st.session_state.chicks_inventory - int(sale_qty))
        st.success(f"{sale_qty} {sale_type}s sold to {sale_customer} on {sale_dt}")

    st.markdown("#### Sales Record")
    st.dataframe([
        {
            "Date": sale["date"],
            "Customer": sale["name"],
            "Type": sale["type"],
            "Quantity": sale["count"],
        } for sale in st.session_state.sales
    ])

    total_sales = sum(sale["count"] for sale in st.session_state.sales if sale["type"] == "Chick")
    total_cocks = sum(sale["count"] for sale in st.session_state.sales if sale["type"] == "Cock")
    total_pol = sum(sale["count"] for sale in st.session_state.sales if sale["type"] == "Point of Lay")

    st.info(
        f"Total chicks sold: {total_sales}\n"
        f"Total cocks sold: {total_cocks}\n"
        f"Total point-of-lay sold: {total_pol}"
    )

    # Summary totals and chart for Sales
    st.markdown("##### Sales Summary & Chart")
    st.write(f"Chicks sold: {total_sales} — Cocks sold: {total_cocks} — POL sold: {total_pol}")
    # Sales by date for chicks
    sales_by_date = {}
    for s in st.session_state.sales:
        if s.get('type') == 'Chick':
            d = s.get('date')
            sales_by_date[d] = sales_by_date.get(d, 0) + s.get('count', 0)
    if sales_by_date:
        dates = sorted(sales_by_date.keys())
        counts = [sales_by_date[d] for d in dates]
        st.line_chart({"Chicks sold": counts})
        st.table([{"Date": d, "Sold": sales_by_date[d]} for d in dates])

# -- END OF APP --
st.markdown("---")
st.caption(
    "Built for demonstration. Data resets on rerun unless persisted externally."
)