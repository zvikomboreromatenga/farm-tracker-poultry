import datetime
from streamlit.runtime.scriptrunner import RerunException
import streamlit as st

# Import the app module (relies on top-level Streamlit session_state initialization)
import importlib


def setup_session_state():
    # Ensure a clean session_state for tests
    st.session_state.clear()
    # initialize expected keys like the app does
    st.session_state.egg_inventory = {}
    st.session_state.hatchery = []
    st.session_state.chicks_orders = []
    st.session_state.chicks_inventory = 0
    st.session_state.sales = []
    st.session_state.processed_hatch_dates = []


def test_fifo_allocation_from_inventory(monkeypatch):
    import streamlit_app as app
    setup_session_state()
    today = datetime.date.today()
    # immediate inventory: 10 chicks
    st.session_state.chicks_inventory = 10
    # orders: two orders, FIFO
    st.session_state.chicks_orders = [
        {'name': 'A', 'order_count': 6, 'order_date': today, 'picked_up': False},
        {'name': 'B', 'order_count': 4, 'order_date': today, 'picked_up': False},
    ]
    res = app.forecast_pickup_dates()
    # both should be assigned to today
    assert res[0]['pickup_date'] == today
    assert res[1]['pickup_date'] == today


def test_allocate_from_hatchery_before_incubators(monkeypatch):
    import streamlit_app as app
    setup_session_state()
    today = datetime.date.today()
    # hatchery scheduled hatches in 2 days: 5 chicks
    hdate = today + datetime.timedelta(days=2)
    st.session_state.hatchery = [{'date': hdate, 'location': 'X', 'chicks': 5}]
    # incubator eggs that will hatch later (3 weeks)
    inc_date = today
    st.session_state.egg_inventory = {inc_date: 100}  # would produce 85 chicks at 3 weeks
    # orders: one for 5 (should be assigned to hatchery date)
    st.session_state.chicks_orders = [
        {'name': 'C', 'order_count': 5, 'order_date': today, 'picked_up': False},
    ]
    res = app.forecast_pickup_dates()
    assert res[0]['pickup_date'] == hdate


def test_unfulfillable_order_not_assigned(monkeypatch):
    import streamlit_app as app
    setup_session_state()
    today = datetime.date.today()
    # availability: day1=5, day2=5 (no single date can fill 8)
    st.session_state.hatchery = [{'date': today, 'location': 'X', 'chicks': 5},
                                {'date': today + datetime.timedelta(days=1), 'location': 'Y', 'chicks': 5}]
    st.session_state.chicks_orders = [
        {'name': 'D', 'order_count': 8, 'order_date': today, 'picked_up': False},
    ]
    res = app.forecast_pickup_dates()
    assert res[0]['pickup_date'] is None


def test_allocate_to_later_sufficient_date(monkeypatch):
    import streamlit_app as app
    setup_session_state()
    today = datetime.date.today()
    # today has 3, day2 has 10
    st.session_state.hatchery = [{'date': today, 'location': 'A', 'chicks': 3},
                                {'date': today + datetime.timedelta(days=2), 'location': 'B', 'chicks': 10}]
    st.session_state.chicks_orders = [
        {'name': 'E', 'order_count': 8, 'order_date': today, 'picked_up': False},
    ]
    res = app.forecast_pickup_dates()
    assert res[0]['pickup_date'] == today + datetime.timedelta(days=2)


def test_fifo_skips_unfulfillable_and_fulfills_later_orders(monkeypatch):
    import streamlit_app as app
    setup_session_state()
    today = datetime.date.today()
    # today has 5
    st.session_state.hatchery = [{'date': today, 'location': 'A', 'chicks': 5}]
    # two orders: first 6 (can't be filled), second 5 (can be filled)
    st.session_state.chicks_orders = [
        {'name': 'F1', 'order_count': 6, 'order_date': today, 'picked_up': False},
        {'name': 'F2', 'order_count': 5, 'order_date': today, 'picked_up': False},
    ]
    res = app.forecast_pickup_dates()
    assert res[0]['pickup_date'] is None
    assert res[1]['pickup_date'] == today
