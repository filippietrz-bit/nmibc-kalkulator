import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

# Konfiguracja strony
st.set_page_config(
    page_title="NMIBC Risk Manager EAU 2025",
    page_icon="⚕️",
    layout="wide"
)

# Style CSS
st.markdown("""
    <style>
    .risk-card {
        padding: 20px;
        border-radius: 15px;
        color: white;
        margin-bottom: 20px;
    }
    .very-high { background-color: #0f172a; border: 2px solid #000; }
    .high { background-color: #dc2626; border: 2px solid #991b1b; }
    .intermediate { background-color: #fbbf24; color: black; border: 2px solid #d97706; }
    .low { background-color: #10b981; border: 2px solid #059669; }
    .footer { margin-top: 50px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 0.8em; color: #666; }
    </style>
""", unsafe_allow_html=True)

# Baza protokołów
PROTOCOLS = {
    'low': {
        'level': 'Niskie (Low)',
        'class': 'low',
        'rec': 'Niskie ryzyko - obserwacja po pojedynczej wlewce.',
        'treatment': "Pojedyncza wlewka chemioterapeutyku (np. Mitomycyna C, Gemcytabina) bezpośrednio po TURBT (do 24h).",
        'bcg': None,
        'schedule': [],
        'followup': "Cystoskopia w 3. miesiącu. Jeśli negatywna: kolejna w 12. miesiącu, następnie raz w roku przez 5 lat. Nie wymaga rutynowej TK górnych dróg moczowych."
    },
    'intermediate': {
        'level': 'Pośrednie (Intermediate)',
        'class': 'intermediate',
        'rec': 'Grupa heterogenna. Indywidualizacja leczenia.',
        'treatment': "Adiuwantowa chemioterapia (maks. 1 rok) lub BCG (1 rok). Decyzja zależy od indywidualnego ryzyka nawrotu.",
        'bcg': "Indukcja: 6 wlewek co tydzień. Podtrzymywanie: 3 wlewki co tydzień w miesiącach 3, 6, 12.",
        'schedule': [3, 6, 12],
        'followup': "Cystoskopia w 3, 6, 12 miesiącu, następnie co rok przez 5 lat. TK urografia (URO-TK) tylko przy wskazaniach klinicznych."
    },
    'high': {
        'level': 'Wysokie (High)',
        'class': 'high',
        'rec': 'Wymagane leczenie podtrzymujące BCG.',
        'treatment': "Pełna dawka BCG przez 1-3 lata (standard). W przypadku nietolerancji/braku dostępności: chemioterapia wlewek.",
        'bcg': "Indukcja: 6 wlewek co tydzień. Podtrzymywanie (SWOG): 3 wlewki co tydzień w mies. 3, 6, 12, 18, 24, 30, 36.",
        'schedule': [3, 6, 12, 18, 24, 30, 36],
        'followup': "Cystoskopia i cytologia: co 3 mies. przez 2 lata, potem co 6 mies. do 5 lat, następnie co rok. TK urografia (URO-TK) co 1-2 lata (kontrola górnych dróg moczowych)."
    },
    'veryHigh': {
        'level': 'Bardzo Wysokie (Very High)',
        'class': 'very-high',
        'rec': 'Najwyższe ryzyko progresji i zgonu. Rozważ wczesną cystektomię (RC).',
        'treatment': "Standardem jest wczesna Radykalna Cystektomia (RC). Jeśli pacjent odmawia lub jest niekwalifikowalny: BCG przez 1-3 lata.",
        'bcg': "Indukcja: 6 wlewek co tydzień. Podtrzymywanie: 3 wlewki co tydzień w mies. 3, 6, 12, 18, 24, 30, 36. Przy jakimkolwiek niepowodzeniu -> natychmiastowa RC.",
        'schedule': [3, 6, 12, 18, 24, 30, 36],
        'followup': "Ścisły nadzór! Cystoskopia i cytologia co 3 mies. przez 2 lata, potem co 6 mies. TK urografia (URO-TK) co 1 rok. Biopsje mapujące przy podejrzeniu wznowy."
    }
}

# Funkcja obliczania ryzyka
def calculate_risk(data, crf_count):
    if data['hasLVI'] or data['hasVariantHistology'] or data['hasProstaticCIS']:
        return 'veryHigh'
    
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

# --- UI ---

col_main, col_result = st.columns([1, 1.2])

with col_main:
    st.title("⚕️ NMIBC Risk Manager")
    st.caption("Zgodne z EAU Guidelines 2025")
    
    st.markdown("### 📅 Kliniczne Czynniki Ryzyka (CRF)")
    age = st.radio("Wiek > 70 lat", ['Nie', 'Tak'], horizontal=True)
    count = st.radio("Mnogie guzy", ['Nie', 'Tak'], horizontal=True)
    size = st.radio("Średnica >= 3 cm", ['Nie', 'Tak'], horizontal=True)
    
    crf_count = 0
    if age == 'Tak': crf_count += 1
    if count == 'Tak': crf_count += 1
    if size == 'Tak': crf_count += 1
    st.info(f"Suma CRF: {crf_count}")

    st.markdown("### 🎯 Histopatologia")
    t_cat = st.selectbox("Kategoria T", ['Ta', 'T1', 'Tis'])
    grade = st.selectbox("Grade", ['LG', 'HG'], disabled=(t_cat=='Tis'))
    is_primary = st.radio("Status", ['Pierwotny', 'Nawrotowy'], horizontal=True)

    st.markdown("### ⚠️ Czynniki Very High")
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

    st.subheader("💉 Plan Leczenia")
    st.write(f"**Zalecenie:** {result['treatment']}")

    if result['bcg']:
        with st.expander("📅 Harmonogram Wlewek (Kalkulator)", expanded=True):
            st.info(f"**Protokół:** {result['bcg']}")
            induction_date = st.date_input("Data 1. wlewki indukcyjnej", value=None)
            
            if induction_date and result['schedule']:
                st.markdown("**Starty cykli podtrzymujących (3-tygodniowych):**")
                schedule_data = []
                for offset in result['schedule']:
                    cycle_date = induction_date + timedelta(days=offset*30) 
                    schedule_data.append({
                        "Miesiąc": offset,
                        "Data orientacyjna": cycle_date.strftime("%d.%m.%Y")
                    })
                st.table(pd.DataFrame(schedule_data))

    st.subheader("👁️ Follow-up")
    st.success(result['followup'])

    st.markdown("""
    <div class="footer">
        <b>lek. Filip Pietrzak</b><br>
        Oddział Urologii Międzyleskiego Szpitala Specjalistycznego
    </div>
    """, unsafe_allow_html=True)
