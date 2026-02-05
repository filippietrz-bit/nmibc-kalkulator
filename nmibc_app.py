import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import google.generativeai as genai
import os

# --- KONFIGURACJA STRONY ---
st.set_page_config(
    page_title="NMIBC Risk Manager EAU 2025",
    page_icon="⚕️",
    layout="wide"
)

# --- STYLE CSS ---
st.markdown("""
    <style>
    .risk-card { padding: 20px; border-radius: 15px; color: white; margin-bottom: 20px; }
    .very-high { background-color: #0f172a; border: 2px solid #000; }
    .high { background-color: #dc2626; border: 2px solid #991b1b; }
    .intermediate { background-color: #fbbf24; color: black; border: 2px solid #d97706; }
    .low { background-color: #10b981; border: 2px solid #059669; }
    .footer { margin-top: 50px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.8em; color: #666; }
    .chat-message { padding: 10px; border-radius: 10px; margin-bottom: 10px; }
    .chat-user { background-color: #eff6ff; border-left: 4px solid #2563eb; text-align: right; }
    .chat-model { background-color: #f8fafc; border-left: 4px solid #64748b; }
    </style>
""", unsafe_allow_html=True)

# --- KONFIGURACJA GEMINI API ---
# Klucz będzie pobierany z "Secrets" w Streamlit Cloud dla bezpieczeństwa
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.0-flash')
    ai_available = True
except Exception:
    ai_available = False

# --- BAZA PROTOKOŁÓW (EAU 2025) ---
PROTOCOLS = {
    'low': {
        'level': 'Niskie (Low)', 'class': 'low',
        'rec': 'Niskie ryzyko - obserwacja po pojedynczej wlewce.',
        'treatment': "Pojedyncza wlewka chemioterapeutyku (np. Mitomycyna C, Gemcytabina) bezpośrednio po TURBT (do 24h).",
        'bcg': None, 'schedule': [],
        'followup': "Cystoskopia w 3. miesiącu. Jeśli negatywna: kolejna w 12. miesiącu, następnie raz w roku przez 5 lat."
    },
    'intermediate': {
        'level': 'Pośrednie (Intermediate)', 'class': 'intermediate',
        'rec': 'Grupa heterogenna. Indywidualizacja leczenia.',
        'treatment': "Adiuwantowa chemioterapia (maks. 1 rok) lub BCG (1 rok). Decyzja zależy od indywidualnego ryzyka nawrotu.",
        'bcg': "Indukcja: 6 wlewek co tydzień. Podtrzymywanie: 3 wlewki co tydzień w miesiącach 3, 6, 12.",
        'schedule': [3, 6, 12],
        'followup': "Cystoskopia w 3, 6, 12 miesiącu, następnie co rok przez 5 lat. TK urografia (URO-TK) przy wskazaniach."
    },
    'high': {
        'level': 'Wysokie (High)', 'class': 'high',
        'rec': 'Wymagane leczenie podtrzymujące BCG.',
        'treatment': "Pełna dawka BCG przez 1-3 lata (standard). W przypadku nietolerancji: chemioterapia.",
        'bcg': "Indukcja: 6x co tydzień. Podtrzymywanie (SWOG): 3x co tydzień w mies. 3, 6, 12, 18, 24, 30, 36.",
        'schedule': [3, 6, 12, 18, 24, 30, 36],
        'followup': "Cystoskopia i cytologia: co 3 mies. przez 2 lata, potem co 6 mies. do 5 lat. TK urografia co 1-2 lata."
    },
    'veryHigh': {
        'level': 'Bardzo Wysokie (Very High)', 'class': 'very-high',
        'rec': 'Najwyższe ryzyko progresji. Rozważ wczesną cystektomię (RC).',
        'treatment': "Standard: wczesna Radykalna Cystektomia (RC). Jeśli brak zgody: BCG 1-3 lata.",
        'bcg': "Indukcja: 6x co tydzień. Podtrzymywanie: 3x co tydzień w mies. 3, 6, 12, 18, 24, 30, 36. Przy niepowodzeniu -> RC.",
        'schedule': [3, 6, 12, 18, 24, 30, 36],
        'followup': "Ścisły nadzór! Cystoskopia i cytologia co 3 mies. przez 2 lata. TK urografia co 1 rok. Biopsje mapujące."
    }
}

# --- FUNKCJA OBLICZANIA RYZYKA ---
def calculate_risk(data, crf_count):
    if data['hasLVI'] or data['hasVariantHistology'] or data['hasProstaticCIS']: return 'veryHigh'
    
    is_very_high_table = False
    if data['hasCIS']:
        if data['tCategory'] == 'Ta' and data['grade'] == 'HG' and crf_count == 3: is_very_high_table = True
        if data['tCategory'] == 'T1' and data['grade'] == 'HG' and crf_count >= 1: is_very_high_table = True
    else:
        if data['tCategory'] == 'T1' and data['grade'] == 'HG' and crf_count == 3: is_very_high_table = True
    if is_very_high_table: return 'veryHigh'

    is_high = False
    if data['tCategory'] == 'Tis' or data['hasCIS']: is_high = True
    if data['tCategory'] == 'T1' and data['grade'] == 'HG': is_high = True
    if not data['hasCIS']:
        if data['tCategory'] == 'Ta' and data['grade'] == 'LG' and crf_count == 3: is_high = True
        if data['tCategory'] == 'Ta' and data['grade'] == 'HG' and crf_count >= 2: is_high = True
        if data['tCategory'] == 'T1' and data['grade'] == 'LG' and crf_count >= 2: is_high = True
    if is_high: return 'high'

    if data['isPrimary'] and not data['hasCIS'] and data['tCategory'] == 'Ta' and data['grade'] == 'LG':
        if (data['tumorCount'] == 'single' and data['tumorSize'] == '<3cm' and data['age'] == '<=70') or crf_count <= 1:
            return 'low'

    return 'intermediate'

# --- INTERFEJS UŻYTKOWNIKA ---
col_main, col_result = st.columns([1, 1.2])

with col_main:
    st.title("⚕️ NMIBC Risk Manager")
    st.caption("EAU Guidelines 2025 • AI Enhanced")
    
    st.markdown("### 📅 Kliniczne Czynniki Ryzyka (CRF)")
    c1, c2, c3 = st.columns(3)
    with c1: age = st.radio("Wiek > 70 lat", ['Nie', 'Tak'])
    with c2: count = st.radio("Mnogie guzy", ['Nie', 'Tak'])
    with c3: size = st.radio("Średnica >= 3 cm", ['Nie', 'Tak'])
    
    crf_count = (1 if age == 'Tak' else 0) + (1 if count == 'Tak' else 0) + (1 if size == 'Tak' else 0)
    st.info(f"Suma CRF: {crf_count}")

    st.markdown("### 🎯 Histopatologia")
    c4, c5 = st.columns(2)
    with c4: t_cat = st.selectbox("Kategoria T", ['Ta', 'T1', 'Tis'])
    with c5: grade = st.selectbox("Grade", ['LG', 'HG'], disabled=(t_cat=='Tis'))
    is_primary = st.radio("Status", ['Pierwotny', 'Nawrotowy'], horizontal=True)

    with st.expander("⚠️ Czynniki Very High"):
        has_cis = st.checkbox("Współistniejący CIS")
        has_lvi = st.checkbox("Inwazja LVI")
        has_variant = st.checkbox("Wariant histologiczny")
        has_prostatic = st.checkbox("CIS cewki sterczowej")

    form_data = {
        'age': '>70' if age == 'Tak' else '<=70',
        'tumorCount': 'multiple' if count == 'Tak' else 'single',
        'tumorSize': '>=3cm' if size == 'Tak' else '<3cm',
        'tCategory': t_cat,
        'grade': 'HG' if t_cat == 'Tis' else grade,
        'isPrimary': (is_primary == 'Pierwotny'),
        'hasCIS': has_cis,
        'hasLVI': has_lvi,
        'hasVariantHistology': has_variant,
        'hasProstaticCIS': has_prostatic
    }

with col_result:
    risk_key = calculate_risk(form_data, crf_count)
    result = PROTOCOLS[risk_key]

    st.markdown(f"""
    <div class="risk-card {result['class']}">
        <div style="font-size: 0.8em; opacity: 0.8; letter-spacing: 2px;">GRUPA RYZYKA EAU</div>
        <div style="font-size: 2.5em; font-weight: 900;">{result['level']}</div>
        <hr style="border-color: rgba(255,255,255,0.2);">
        <div>{result['rec']}</div>
    </div>
    """, unsafe_allow_html=True)

    # --- SEKCJON AI GENERATOR ---
    if ai_available:
        if st.button("✨ Generuj wyjaśnienie dla pacjenta (AI)"):
            with st.spinner("Analizuję wytyczne i generuję list..."):
                prompt = f"""
                Jesteś urologiem. Napisz empatyczną notatkę DLA PACJENTA.
                Pacjent ma: {result['level']} (NMIBC).
                Plan: {result['treatment']}.
                Wyjaśnij prostym językiem diagnozę, leczenie i konieczność kontroli ({result['followup']}).
                Bądź konkretny ale uspokajający. Używaj języka polskiego.
                """
                response = model.generate_content(prompt)
                st.success("Gotowe!")
                st.text_area("List dla pacjenta (do skopiowania):", value=response.text, height=300)
    else:
        st.warning("Skonfiguruj klucz API Gemini, aby używać funkcji AI.")

    st.subheader("💉 Plan Leczenia")
    st.write(f"**Zalecenie:** {result['treatment']}")

    if result['bcg']:
        with st.expander("📅 Harmonogram Wlewek", expanded=True):
            st.info(f"**Protokół:** {result['bcg']}")
            induction_date = st.date_input("Data 1. wlewki indukcyjnej", value=None)
            
            if induction_date and result['schedule']:
                st.markdown("**Starty cykli podtrzymujących:**")
                schedule_data = []
                for offset in result['schedule']:
                    cycle_date = induction_date + timedelta(days=offset*30) 
                    schedule_data.append({"Miesiąc": offset, "Data orientacyjna": cycle_date.strftime("%d.%m.%Y")})
                st.dataframe(pd.DataFrame(schedule_data), hide_index=True)

    st.subheader("👁️ Follow-up")
    st.success(result['followup'])

    # --- SEKCJON AI CHAT ---
    if ai_available:
        with st.expander("💬 Konsultant EAU (Czat AI)"):
            if "messages" not in st.session_state:
                st.session_state.messages = []

            for message in st.session_state.messages:
                cls = "chat-user" if message["role"] == "user" else "chat-model"
                st.markdown(f"<div class='chat-message {cls}'>{message['content']}</div>", unsafe_allow_html=True)

            if prompt := st.chat_input("Zadaj pytanie dotyczące tego przypadku..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                st.markdown(f"<div class='chat-message chat-user'>{prompt}</div>", unsafe_allow_html=True)

                context = f"Pacjent: {form_data['age']}, {form_data['tCategory']} {form_data['grade']}, Grupa: {result['level']}. Pytanie: {prompt}"
                ai_reply = model.generate_content(context).text
                
                st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                st.rerun()

    st.markdown("""
    <div class="footer">
        <b>lek. Filip Pietrzak</b><br>
        Oddział Urologii Międzyleskiego Szpitala Specjalistycznego
    </div>
    """, unsafe_allow_html=True)
