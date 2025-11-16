import os
import re
import pandas as pd
import streamlit as st
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except Exception:
    DUCKDB_AVAILABLE = False

st.set_page_config(
    page_title="Dashboard SKPG UM",
    page_icon="lencana.jpg",
    layout="wide"
)

# --- PATHS AND FILE DISCOVERY ---
script_dir = os.path.dirname(os.path.abspath(__file__))
data_folder = os.path.join(script_dir, "Data SKPG")
os.makedirs(data_folder, exist_ok=True)

xlsx_pattern = re.compile(r"Data SKPG (\d{4})\.xlsx")

def ensure_parquet_from_excel(xlsx_path: str, parquet_path: str, sheet: str = "DATASET") -> None:
    if not DUCKDB_AVAILABLE:
        return

    if not os.path.exists(xlsx_path):
        return

    needs_convert = True
    if os.path.exists(parquet_path):
        needs_convert = os.path.getmtime(parquet_path) < os.path.getmtime(xlsx_path)

    if not needs_convert:
        return

    os.makedirs(os.path.dirname(parquet_path), exist_ok=True)
    con = duckdb.connect()
    try:
        con.execute("INSTALL excel; LOAD excel;")
        con.execute(f"""
            COPY (
                SELECT * FROM read_excel('{xlsx_path}', sheet='{sheet}')
            ) TO '{parquet_path}' (FORMAT PARQUET);
        """)
    finally:
        con.close()

def build_year_maps(folder: str):
    xlsx_map = {}
    parquet_map = {}

    for fname in os.listdir(folder):
        m = xlsx_pattern.match(fname)
        if not m:
            continue
        year = m.group(1)
        xlsx_path = os.path.join(folder, fname)
        parquet_path = os.path.join(folder, f"Data SKPG {year}.parquet")

        if DUCKDB_AVAILABLE:
            try:
                ensure_parquet_from_excel(xlsx_path, parquet_path, sheet="DATASET")
                if os.path.exists(parquet_path):
                    parquet_map[year] = parquet_path
            except Exception:
                pass

        xlsx_map[year] = xlsx_path

    return xlsx_map, parquet_map

xlsx_files_by_year, parquet_files_by_year = build_year_maps(data_folder)
available_years = sorted(
    (parquet_files_by_year.keys() or xlsx_files_by_year.keys()),
    reverse=True
)

# --- FAST LOADERS ---
@st.cache_data(show_spinner=False)
def load_all_parquet(files_by_year: dict) -> pd.DataFrame:
    dfs = []
    for year, path in files_by_year.items():
        dfp = pd.read_parquet(path)
        if "SKPG_Tahun" not in dfp.columns:
            dfp["SKPG_Tahun"] = year
        else:
            dfp["SKPG_Tahun"] = dfp["SKPG_Tahun"].astype(str).replace({"nan": year})
        dfs.append(dfp)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

@st.cache_data(show_spinner=False)
def load_all_excel(files_by_year: dict, usecols=None) -> pd.DataFrame:
    dfs = []
    for year, path in files_by_year.items():
        df = pd.read_excel(
            io=path,
            engine="openpyxl",
            sheet_name="DATASET",
            skiprows=0,
            usecols=usecols
        )
        df["SKPG_Tahun"] = year
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

try:
    if parquet_files_by_year:
        df = load_all_parquet(parquet_files_by_year)
    else:
        df = load_all_excel(xlsx_files_by_year)
except Exception:
    df = load_all_excel(xlsx_files_by_year)

if df.empty:
    st.warning("Tiada data dijumpai.")
    st.stop()

for col in df.select_dtypes(include="object").columns:
    try:
        df[col] = df[col].str.title()
    except Exception:
        pass

# --- FILTERS ON TOP ---
warganegara_map = {
    "1": "Warganegara", 
    "2": "Bukan Warganegara"
}
status_pekerjaan_map = {
    "-2": "Tidak Berkenaan",
    "1": "Bekerja",
    "2": "Belum/Tidak Bekerja",
    "4": "Bekerja Sepenuh Masa",
    "7": "Melanjutkan Pengajian",
    "52": "Bekerja (Mempunyai Majikan/Bekerja Sendiri/Usahawan/Freelance)",
    "90": "Menganggur",
    "91": "Penganggur Aktif",
    "92": "Penganggur Tidak Aktif",
    "93": "Luar Tenaga Buruh"
}
status_kerjage_map = {
    "-2": "Tidak Berkenaan",
    "1": "Bekerja",
    "5": "Belum Bekerja"
}
status_kerja_map = {
    "0": "Tiada Maklumat",
    "1": "Bekerja",
    "2": "Melanjutkan Pengajian",
    "3": "Meningkatkan kemahiran",
    "4": "Menunggu penempatan pekerjaan",
    "5": "Belum Bekerja",
}
status_penyertaan_map = {
    "1" : "Sertai",
    "2" : "Tidak/Belum Sertai",
    "3" : "Tidak Lengkap",
}
sebab_tidak_bekerja_map = {
    "1": "Melanjutkan Pengajian",
    "5": "Sedang Mencari Pekerjaan",
    "7": "Tanggungjawab Terhadap Keluarga",
    "8": "Kurang Keyakinan Diri Untuk Memasuki Dunia Pekerjaan",
    "10": "Memilih Untuk Tidak Bekerja",
    "11": "Tidak Berminat Untuk Bekerja",
    "13": "Menunggu Penempatan Pekerjaan (Telah Menerima Tawaran Pekerjaan)",
    "14": "Mengikut Kursus Jangka Pendek",
    "15": "Berehat/Melancong/Bercuti",
    "17": "Menunggu Keputusan/Tawaran Melanjutkan Pengajian",
    "18": "Enggan Berpindah Ke Tempat Lain",
    "20": "Sebab Hilang Upaya",
    "21": "Tidak Dibenarkan Untuk Bekerja Oleh Keluarga",
    "28": "Tidak Dibenarkan Untuk Bekerja Oleh Undang-Undang",
    "30": "Bersara Pilihan/Wajib",
    "31": "Mengikuti Program Inkubasi Usahawan",
    "32": "Sebab Kesihatan (Termasuk Baru Bersalin)",
    "33": "Sedang Mengikuti Kursus Peningkatan Kemahiran",
    "34": "Pekerjaan yang Ditawarkan Tidak Bersesuaian",
}
peringkat_pengajian_map = {
    "1": "Diploma",
    "2": "Diploma Pancasiswazah",
    "3": "PhD",
    "4": "Sarjana Muda",
    "5": "Sarjana",
    "63": "Diploma",
}
fakulti_map = {
    "Fakulti Sains" : "FS",
    "Fakulti Sains Komputer Dan Teknologi Maklumat" : "FSKTM",
    "Fakulti Kejuruteraan" : "FK",
    "Fakulti Perubatan" : "FOM",
    "Fakulti Farmasi" : "FF",
    "Fakulti Undang-Undang" : "FUU",
    "Fakulti Ekonomi Dan Pentadbiran" : "FPE",
    "Fakulti Pendidikan" : "EDU",
    "Fakulti Bahasa Dan Linguistik" : "FBL",
    "Fakulti Alam Bina" : "FAB",
    "Akademi Pengajian Islam" : "API",
    "Akademi Pengajian Melayu" : "APM",
    "Fakulti Sastera Dan Sains Sosial" : "FSSS",
    "Fakulti Seni Kreatif" : "FSK",
    "Pusat Kebudayaan" : "FSK",
    "Fakulti Pergigian" : "FOD",
    "Fakulti Perniagaan Dan Ekonomi" : "FPE",
    "Institut Asia Eropah" : "AEI",
    "Institut Pengajian Termaju" : "IAS",
    "Int Antarabangsa Polisi Awam Dan Pengurusan (Inpuma)" : "INPUMA",
    "Fakulti Sukan Dan Sains Eksesais" : "FSSE",
    "Pusat Sukan Dan Sains Eksesais" : "FSSE",
    "Pusat Sukan & Sains Eksesais" : "FSSE",
    "Fakulti Sukan & Sains Eksesais" : "FSSE",
    "University Of Malaya Centre For Continuing Education" : "UMCCED",
    "Umcced" : "UMCCED"
}
sektor_pekerjaan_map = {
    "-2" : "Tidak Berkenaan",
    "2" : "Badan Berkanun",
    "3" : "Syarikat Multinasional",
    "4" : "Syarikat Tempatan",
    "7" : "Syarikat Berkaitan Kerajaan (GLC)",
    "8" : "Perutubuhan Bukan Kerajaan (NGO)",
    "9" : "Kerajaan Persekutuan",
    "10" : "Kerajaan Negeri/Tempatan",
    "11" : "Ekonomi Gig",
}
taraf_pekerjaan_map = {
    "-2" : "Tidak Berkenaan",
    "4" : "Bekerja Sendiri",
    "5" : "Bekerja dengan Keluarga",
    "6" : "Majikan",
    "7" : "Pekerja Kerajaan",
    "8" : "Pekerja Swasta (Termasuk NGO)",
    "9" : "Pekerja (Kerajaan/Swasta/Pekerja Keluarga dengan upah/gaji)",
    "10" : "Pekerja (Kerajaan/Swasta)",
    "40" : "Freelance",
    "46" : "Usahawan",
    "47" : "Bekerja Sendiri (e+p-hailing)",
    "51" : "Bekerja dengan Keluarga (upah/gaji)",
    "52" : "Bekerja dengan Keluarga (tiada upah/gaji)",
}
bekerja_dalam_bidang_map = {
    "-2" : "Tidak Berkenaan",
    "-1" : "Tidak Dinyatakan",
    "1" : "Ya",
    "2" : "Tidak",
}
gaji_kumpulan = {
    "-2" : "Tidak Berkaitan",
    "1" : "RM1,000 dan ke bawah",
    "2" : "RM1,001 - RM1,500",
    "4" : "RM1,501 - RM2,000",
    "5" : "RM2,001 - RM2,500",
    "6" : "RM2,501 - RM3,000",
    "7" : "RM3,001 - RM3,500",
    "8" : "RM3,501 - RM4,000",
    "11" : "RM4,001 - RM5,001",
    "12" : "RM5,001 - RM10,001",
    "13" : "RM5,001 dan ke atas",
    "14" : "Lebih daripada RM10,000",
    "15" : "RM5,001 - RM8,500",
    "16" : "RM8,501 dan ke atas",
}

df = df.copy()

df["e_warganegara_label"] = df.get("e_warganegara", pd.Series(dtype=object)).astype(str).map(warganegara_map)
df["e_40_label"] = df.get("e_40", pd.Series(dtype=object)).astype(str).map(status_pekerjaan_map)
if "e_status_GE2024" in df.columns:
    df["e_status_GE2024_label"] = df["e_status_GE2024"].astype(str).map(status_kerjage_map)
df["e_status_label"] = df.get("e_status", pd.Series(dtype=object)).astype(str).map(status_kerja_map)
df["e_statusPenyertaan_label"] = df.get("e_statusPenyertaan", pd.Series(dtype=object)).astype(str).map(status_penyertaan_map)
df["e_54_label"] = df.get("e_54", pd.Series(dtype=object)).astype(str).map(sebab_tidak_bekerja_map)
df["e_peringkat_label"] = df.get("e_peringkat", pd.Series(dtype=object)).astype(str).map(peringkat_pengajian_map)
df["e_fakulti_label"] = df.get("e_fakulti", pd.Series(dtype=object)).astype(str).map(fakulti_map)
df["e_43_label"] = df.get("e_43", pd.Series(dtype=object)).astype(str).map(taraf_pekerjaan_map)
df["e_45_label"] = df.get("e_45", pd.Series(dtype=object)).astype(str).map(sektor_pekerjaan_map)
df["e_50_b_label"] = df.get("e_50_b", pd.Series(dtype=object)).astype(str).map(bekerja_dalam_bidang_map)
df["e_44_kumpulan_label"] = df.get("e_44_kumpulan", pd.Series(dtype=object)).astype(str).map(gaji_kumpulan)

# --- SESSION STATE DEFAULTS ---

if "selected_years" not in st.session_state:
    st.session_state.selected_years = []
if "selected_warganegara" not in st.session_state:
    st.session_state.selected_warganegara = "Semua"

# --- MEDAN SIDEBAR ---

with st.sidebar:
    warganegara_label_list = [warganegara_map["1"], warganegara_map["2"]]
    
    selected_years = st.multiselect(
        "Pilih Tahun Data SKPG:",
        options=available_years,
        default=st.session_state.selected_years,
        key="selected_years",
        help="Pilih satu, beberapa tahun, atau kosongkan untuk semua tahun."
    )
    if not selected_years:
        tapis_tahun = df
        selected_years = available_years
    else:
        tapis_tahun = df[df['SKPG_Tahun'].astype(str).isin(selected_years)]

    fakulti_list = sorted(tapis_tahun.get("e_fakulti", pd.Series(dtype=object)).dropna().unique())

    selected_warganegara = st.selectbox(
        "Pilih Warganegara:",
        options=["Semua"] + warganegara_label_list,
        index=(["Semua"] + warganegara_label_list).index(st.session_state.selected_warganegara)
            if st.session_state.selected_warganegara in (["Semua"] + warganegara_label_list)
            else 0,
        key="selected_warganegara",
        help="Klik untuk pilih satu atau beberapa status warganegara. Dibiarkan kosong untuk semua."
    )
    if selected_warganegara == "Semua":
        selected_warganegara_tapis = warganegara_label_list
    else:
        selected_warganegara_tapis = [selected_warganegara]

# --- FILTER DATA ---
df_filtered_year = df[
    df['SKPG_Tahun'].astype(str).isin(st.session_state.selected_years if st.session_state.selected_years else available_years)
    & df["e_warganegara_label"].isin([st.session_state.selected_warganegara] if st.session_state.selected_warganegara != "Semua" else warganegara_label_list)
]

# --- DASHBOARD METRICS AND CHARTS ---
def jadual_status_kerja():
    if not df_filtered_year.empty and "e_status_label" in df_filtered_year.columns:
        valid_df = df_filtered_year[df_filtered_year["e_status_label"].str.lower() != "tiada maklumat"]
        status_counts = valid_df["e_status_label"].value_counts().reset_index()
        status_counts.columns = ["Status Bekerja", "Bilangan Graduan"]
        status_counts = status_counts.sort_values(by="Status Bekerja", ascending=True)
        total_graduan = status_counts["Bilangan Graduan"].sum()
        status_counts["Peratusan"] = (status_counts["Bilangan Graduan"] / total_graduan * 100).round(2)
        jumlah_row = pd.DataFrame({
            "Status Bekerja": ["Jumlah"],
            "Bilangan Graduan": [total_graduan],
            "Peratusan": [100.00]
        })
        status_counts = pd.concat([status_counts, jumlah_row], ignore_index=True)
        st.markdown("### Status Bekerja Graduan")
        st.dataframe(status_counts, hide_index=True)

def jadual_peringkat_pengajian():
    if not df_filtered_year.empty and "e_peringkat_label" in df_filtered_year.columns:
        peringkat_counts = df_filtered_year["e_peringkat_label"].value_counts().reset_index()
        peringkat_counts.columns = ["Peringkat Pengajian", "Bilangan Graduan"]
        st.markdown("### Jadual Peringkat Pengajian Graduan")
        st.dataframe(peringkat_counts, hide_index=True)

def graduate_employability_ikut_ptj(df_filtered_year):
    all_fakulti = [
        "API", "APM", "FAB", "FBL", "FF", "FK", "EDU", "FOD", "FPE", "FOM",
        "FS", "FSKTM", "FSSS", "FSK", "FSSE", "FUU", "AEI", "IAS", "INPUMA", "UMCCED"
    ]

    required_cols = ["e_status_label", "e_status", "e_54", "e_fakulti_label"]
    if not all(col in df_filtered_year.columns for col in required_cols):
        st.warning("Kolum yang diperlukan tidak lengkap dalam data.")
        return

    records = []
    for fakulti in all_fakulti:    
        fak_df = df_filtered_year[df_filtered_year["e_fakulti_label"] == fakulti]

        bekerja = fak_df[fak_df["e_status_label"] == "Bekerja"]["e_status_label"].count()
        tidak_bekerja = fak_df[fak_df["e_status_label"] == "Belum Bekerja"]["e_status_label"].count()
        luar_tenaga_buruh = fak_df[
            (fak_df["e_status"] == 5) & 
            (fak_df["e_54"] != 5) & 
            (fak_df["e_54"] != 34)
        ]["e_54"].count()
        total_ge = bekerja + tidak_bekerja - luar_tenaga_buruh
        percent_ge = (bekerja / total_ge * 100) if total_ge > 0 else 0

        if "e_status_label" in fak_df.columns:
            responden = fak_df[fak_df["e_status_label"] != "Tiada Maklumat"]["e_status_label"].count()
            belum_bekerja = fak_df[fak_df["e_status_label"] == "Belum Bekerja"]["e_status_label"].count()
            gm = (responden - belum_bekerja) / responden * 100 if responden > 0 else 0
        else:
            gm = 0

        records.append({
            "Fakulti": fakulti,
            "GE (%)": round(percent_ge, 1),
            "GM (%)": round(gm, 1)
        })

    df_chart = pd.DataFrame(records)
    df_chart = df_chart.melt(
        id_vars="Fakulti", 
        value_vars=["GE (%)", "GM (%)"], 
        var_name="Kadar", 
        value_name="Peratusan"
    )

    st.markdown("##### Kadar GE dan GM")
    fig = px.bar(
        df_chart, 
        x="Fakulti", 
        y="Peratusan", 
        color="Kadar",
        barmode="group",
        text="Peratusan",
        labels={
            "Peratusan": "Peratusan (%)",
            "Fakulti" : "Fakulti",
            "Kadar": "Kadar"
        },
        category_orders={"Fakulti": all_fakulti},
        height=500,
        width=max(1100, 55 * len(all_fakulti))
    )
    fig.update_traces(texttemplate='%{text:.1f}', textposition='inside')
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1,
            xanchor="center",
            x=0.15
        ),
        xaxis_tickangle=-40,
        legend_title="Kadar",
        xaxis_title=None,
        yaxis_title=None,
        margin=dict(l=40, r=40, t=40, b=40),
        uniformtext_minsize=8, 
        uniformtext_mode='hide'
    )
    st.plotly_chart(fig, use_container_width=True)

def kadar_respons_ikut_ptj(df_filtered_year):
    all_fakulti = [
        "API", "APM", "FAB", "FBL", "FF", "FK", "EDU", "FOD", "FPE", "FOM",
        "FS", "FSKTM", "FSSS", "FSK", "FSSE", "FUU", "AEI", "IAS", "INPUMA", "UMCCED"
    ]

    required_cols = ["e_statusPenyertaan", "e_fakulti_label"]
    if not all(col in df_filtered_year.columns for col in required_cols):
        st.warning("Kolum yang diperlukan tidak lengkap dalam data.")
        return

    records = []
    for fakulti in all_fakulti:    
        fak_df = df_filtered_year[df_filtered_year["e_fakulti_label"] == fakulti]
        total = fak_df[fak_df["e_statusPenyertaan"] != -2]["e_statusPenyertaan"].count()
        respon = fak_df[fak_df["e_statusPenyertaan"] == 1]["e_statusPenyertaan"].count()
        rate = (respon / total * 100) if total > 0 else 0
        records.append({
            "Fakulti": fakulti,
            "Kadar Respons": round(rate, 1)
        })

    df_chart = pd.DataFrame(records)

    st.markdown("##### Kadar Respons")
    fig = px.bar(
        df_chart, 
        x="Fakulti", 
        y="Kadar Respons", 
        text="Kadar Respons",
        labels={
            "Kadar Respons": "Kadar Respons (%)",
            "Fakulti" : "Fakulti",
        },
        category_orders={"Fakulti": all_fakulti},
        height=500,
        width=max(1100, 55 * len(all_fakulti)),
    )
    fig.update_traces(marker_color='#0068C9',
                      texttemplate='%{text:.1f}', 
                      textposition='outside',
                      showlegend=False)
    fig.update_layout(
        xaxis_tickangle=-40,
        xaxis_title=None,
        yaxis_title=None,
        margin=dict(l=40, r=40, t=40, b=40),
        uniformtext_minsize=8, 
        uniformtext_mode='hide'
    )
    st.plotly_chart(fig, use_container_width=True)

def bekerja_dalam_bidang_ikut_ptj(df_filtered_year):
    all_fakulti = [
        "API", "APM", "FAB", "FBL", "FF", "FK", "EDU", "FOD", "FPE", "FOM",
        "FS", "FSKTM", "FSSS", "FSK", "FSSE", "FUU", "AEI", "IAS", "INPUMA", "UMCCED"
    ]

    required_cols = ["e_50_b_label", "e_fakulti_label"]
    if not all(col in df_filtered_year.columns for col in required_cols):
        st.warning("Kolum yang diperlukan tidak lengkap dalam data.")
        return

    df_valid = df_filtered_year[df_filtered_year["e_50_b_label"] != "Tidak Berkenaan"].copy()

    records = []
    for fakulti in all_fakulti:
        fak_df = df_valid[df_valid["e_fakulti_label"] == fakulti]
        total = len(fak_df)
        if total == 0:
            continue

        counts = fak_df["e_50_b_label"].value_counts().reset_index()
        counts.columns = ["Status", "Bilangan Graduan"]
        counts["Kadar"] = (counts["Bilangan Graduan"] / total) * 100
        counts["Fakulti"] = fakulti

        records.extend(counts.to_dict("records"))

    df_chart = pd.DataFrame(records)

    st.markdown("###### Bekerja Dalam Bidang (%) mengikut Fakulti")
    fig = px.bar(
        df_chart,
        x="Fakulti",
        y="Kadar",
        color="Status",
        text="Kadar",
        labels={
            "Kadar": "Kadar (%)",
            "Fakulti": "Fakulti",
            "Status": "Bekerja Dalam Bidang"
        },
        category_orders={"Fakulti": all_fakulti},
        height=400,
        width=max(1100, 55 * len(all_fakulti)),
        barmode="stack",
        color_discrete_map={
            "Ya": "#0068C9",
            "Tidak": "#FF4B4B"
        }
    )

    fig.update_traces(
        texttemplate='%{text:.1f}',
        textposition='inside'
    )
    fig.update_layout(
        xaxis_tickangle=-40,
        xaxis_title=None,
        yaxis_title=None,
        margin=dict(l=40, r=40, t=40, b=40),
        uniformtext_minsize=8,
        uniformtext_mode='hide',
        bargap=0.2,
        legend_title_text='Status',
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.3,
            xanchor="center",
            x=0.5
        ),
        yaxis=dict(range=[0, 100])
    )
    st.plotly_chart(fig, use_container_width=True)

def ge_gm_line_tahun(df):
    required_cols = ["SKPG_Tahun", "e_peringkat_label", "e_status_label", "e_status", "e_54"]
    if not all(col in df.columns for col in required_cols):
        st.warning("Kolum yang diperlukan tidak lengkap dalam data.")
        return

    records = []
    for (tahun, peringkat), df_group in df.groupby(["SKPG_Tahun", "e_peringkat_label"]):
        responden = df_group[df_group["e_status_label"] != "Tiada Maklumat"]["e_status_label"].count()
        belum_bekerja = df_group[df_group["e_status_label"] == "Belum Bekerja"]["e_status_label"].count()
        gm = (responden - belum_bekerja) / responden * 100 if responden > 0 else 0

        records.append({
            "SKPG_Tahun": tahun,
            "e_peringkat_label": peringkat,
            "GM (%)": round(gm, 1)
        })
    df_chart = pd.DataFrame(records)
    df_long = df_chart.melt(
        id_vars=["SKPG_Tahun", "e_peringkat_label"], 
        value_vars=["GM (%)"], 
        var_name="Kadar", 
        value_name="Peratusan"
    )
    df_long["Legend"] = df_long["e_peringkat_label"].astype(str)

    st.markdown("##### Kadar GM Mengikut Tahun")
    fig = px.line(
        df_long,
        x="SKPG_Tahun",
        y="Peratusan",
        color="Legend",
        markers=True,
        labels={
            "SKPG_Tahun": "Tahun",
            "Peratusan": "Peratusan (%)",
            "Legend": "Kadar Kebolehpasaran (%)"
        },
        height=300,
        width=850
    )

    for i, d in df_long.iterrows():
        fig.add_annotation(
            x=d["SKPG_Tahun"],
            y=d["Peratusan"],
            text="",
            showarrow=False,
            font=dict(size=11),
            xanchor="center",
            yanchor="bottom"
        )

    fig.update_traces(mode='lines+markers+text')
    fig.update_layout(
        legend_title="Kadar Kebolehpasaran (%)",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.2,
            xanchor="center",
            x=0.4
        ),
        margin=dict(l=40, r=40, t=40, b=40),
        xaxis=dict(title="Tahun"),
        yaxis=dict(title="Peratusan (%)"),
        yaxis_title=None,
    )
    fig.update_xaxes(
        tickvals=df_long["SKPG_Tahun"].unique()
    )
    st.plotly_chart(fig, use_container_width=True)

def table_gm_tahun(df):
    required_cols = ["SKPG_Tahun", "e_peringkat_label", "e_status_label", "e_status", "e_54"]
    if not all(col in df.columns for col in required_cols):
        st.warning("Kolum yang diperlukan tidak lengkap dalam data.")
        return

    records = []
    for (tahun, peringkat), df_group in df.groupby(["SKPG_Tahun", "e_peringkat_label"]):
        responden = df_group[df_group["e_status_label"] != "Tiada Maklumat"]["e_status_label"].count()
        belum_bekerja = df_group[df_group["e_status_label"] == "Belum Bekerja"]["e_status_label"].count()
        gm = (responden - belum_bekerja) / responden * 100 if responden > 0 else 0

        records.append({
            "SKPG_Tahun": tahun,
            "e_peringkat_label": peringkat,
            "GM (%)": round(gm, 1)
        })
    df_chart = pd.DataFrame(records)

    gm_table = df_chart.pivot(index="e_peringkat_label", columns="SKPG_Tahun", values="GM (%)")
    gm_table = gm_table.rename_axis("Peringkat Pengajian", axis="index")
    gm_table = gm_table.sort_index(axis=0).sort_index(axis=1) 
    gm_table = gm_table.map(lambda x: f"{x:.1f}" if pd.notnull(x) else "")
    st.dataframe(gm_table, use_container_width=True)

def ge_gm_keseluruhan(df_filtered_year):
    required_cols = [
        "e_status_label", "e_status", "e_54", "SKPG_Tahun", "e_statusPenyertaan_label"
    ]
    if not all(col in df_filtered_year.columns for col in required_cols):
        st.warning("Kolum yang diperlukan tidak lengkap dalam data.")
        return

    kadar_respons_dict = {}
    for tahun in df["SKPG_Tahun"].dropna().unique():
        tahun_df = df[df["SKPG_Tahun"] == tahun]
        total_responden = tahun_df["e_statusPenyertaan"].count()
        total_lengkap = tahun_df[tahun_df["e_statusPenyertaan"] == 1]["e_statusPenyertaan"].count()
        kadar_respons = (total_lengkap / total_responden * 100) if total_responden > 0 else 0
        kadar_respons_dict[tahun] = round(kadar_respons, 1)

    records = []
    line_records = []
    for tahun in sorted(df["SKPG_Tahun"].dropna().unique()):
        thn_df = df[df["SKPG_Tahun"] == tahun]

        bekerja = thn_df[thn_df["e_status_label"] == "Bekerja"]["e_status_label"].count()
        tidak_bekerja = thn_df[thn_df["e_status_label"] == "Belum Bekerja"]["e_status_label"].count()
        luar_tenaga_buruh = thn_df[
            (thn_df["e_status"] == 5) & 
            (thn_df["e_54"] != 5) & 
            (thn_df["e_54"] != 34)
        ]["e_54"].count()
        total_ge = bekerja + tidak_bekerja - luar_tenaga_buruh
        percent_ge = (bekerja / total_ge * 100) if total_ge > 0 else 0

        responden = thn_df[thn_df["e_status_label"] != "Tiada Maklumat"]["e_status_label"].count()
        belum_bekerja = thn_df[thn_df["e_status_label"] == "Belum Bekerja"]["e_status_label"].count()
        gm = (responden - belum_bekerja) / responden * 100 if responden > 0 else 0

        records.append({
            "Tahun": tahun,
            "GE (%)": round(percent_ge, 1),
            "GM (%)": round(gm, 1)
        })
        line_records.append({
            "Tahun": tahun,
            "Kadar Respons": kadar_respons_dict.get(tahun, 0)
        })

    df_chart = pd.DataFrame(records)
    df_chart = df_chart.melt(
        id_vars="Tahun", 
        value_vars=["GE (%)", "GM (%)"], 
        var_name="Kadar", 
        value_name="Peratusan"
    )
    df_line = pd.DataFrame(line_records)

    st.markdown("##### Kadar Respons, GE dan GM Mengikut Tahun")

    fig = go.Figure()

    for k in df_chart['Kadar'].unique():
        bar_df = df_chart[df_chart['Kadar'] == k]
        fig.add_trace(go.Bar(
            x=bar_df['Tahun'],
            y=bar_df['Peratusan'],
            name=k,
            text=bar_df['Peratusan'],
            textposition='inside'
        ))

    fig.add_trace(go.Scatter(
        x=df_line['Tahun'],
        y=df_line['Kadar Respons'],
        name='Kadar Respons (%)',
        mode='lines+markers+text',
        text=df_line['Kadar Respons'],
        textposition='top center',
        marker=dict(color='black', symbol='circle', size=10),
        line=dict(color='black', width=2, dash='dash')
    ))

    fig.update_layout(
        barmode='group',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.08,
            xanchor="center",
            x=0.5
        ),
        xaxis_tickangle=0,
        legend_title="Kadar",
        xaxis_title="Tahun",
        yaxis_title=None,
        margin=dict(l=40, r=40, t=40, b=40),
        uniformtext_minsize=8, 
        uniformtext_mode='hide',
        height=550,
        width=max(600, 90 * df_chart['Tahun'].nunique())
    )

    st.plotly_chart(fig, use_container_width=True)

def kemahiran_kerja(df_filtered_year):
    all_fakulti = [
        "API", "APM", "FAB", "FBL", "FF", "FK", "EDU", "FOD", "FPE", "FOM",
        "FS", "FSKTM", "FSSS", "FSK", "FSSE", "FUU", "AEI", "IAS", "INPUMA", "UMCCED"
    ]

    mahir_codes = [1, 2, 3]
    separa_mahir_codes = [4, 5, 6, 7, 8, 10]
    rendah_codes = [9]

    results = []
    for fakulti in all_fakulti:
        fak_df = df_filtered_year[df_filtered_year["e_fakulti_label"] == fakulti]
        kerja_df = fak_df[fak_df["e_41_a"] != -2]

        total_kerja = kerja_df["e_41_a"].count()
        if total_kerja == 0:
            mahir_pct = separa_mahir_pct = rendah_pct = 0
        else:
            mahir = kerja_df[kerja_df["e_41_a"].isin(mahir_codes)]["e_41_a"].count()
            separa_mahir = kerja_df[kerja_df["e_41_a"].isin(separa_mahir_codes)]["e_41_a"].count()
            rendah = kerja_df[kerja_df["e_41_a"].isin(rendah_codes)]["e_41_a"].count()
            mahir_pct = round(mahir / total_kerja * 100, 1)
            separa_mahir_pct = round(separa_mahir / total_kerja * 100, 1)
            rendah_pct = round(rendah / total_kerja * 100, 1)

        results.append({
            "Fakulti": fakulti,
            "Mahir (%)": mahir_pct,
            "Separa Mahir (%)": separa_mahir_pct,
            "Berkemahiran Rendah (%)": rendah_pct,
        })

    df_skill = pd.DataFrame(results)
    df_melted = df_skill.melt(
        id_vars="Fakulti",
        value_vars=["Mahir (%)", "Separa Mahir (%)", "Berkemahiran Rendah (%)"],
        var_name="Kategori",
        value_name="Peratusan"
    )

    st.markdown("###### Tahap Kemahiran Kerja (%)")

    fig = px.bar(
        df_melted,
        x="Fakulti",
        y="Peratusan",
        color="Kategori",
        text="Peratusan",
        barmode="stack",
        labels={
            "Fakulti": "Fakulti",
            "Peratusan": "Peratusan (%)",
            "Kategori": "Kategori Kemahiran"
        },
        category_orders={"Fakulti": all_fakulti}
    )

    fig.update_traces(texttemplate='%{text:.1f}', textposition='inside')
    fig.update_layout(
        xaxis_tickangle=-40,
        yaxis=dict(range=[0, 100]),
        xaxis_title=None,
        yaxis_title=None,
        margin=dict(l=40, r=40, t=40, b=40),
        legend_title="Kategori Kemahiran",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=1.3,
            xanchor="center",
            x=0.5
        ),
        height=400,
        width=75 * len(all_fakulti)
    )
    st.plotly_chart(fig, use_container_width=True)

def gaji_ikut_kumpulan_donut_phd(df_filtered_year):
    donut_df = df_filtered_year[df_filtered_year["e_peringkat_label"] == "PhD"]
    if "e_44_kumpulan" not in donut_df.columns or donut_df.empty:
        st.warning("Tiada data gaji untuk peringkat PhD.")
        return

    kumpulan_gaji = pd.to_numeric(donut_df["e_44_kumpulan"], errors='coerce')
    mask_valid = ~kumpulan_gaji.isna() & (kumpulan_gaji != -2)
    kumpulan_gaji = kumpulan_gaji[mask_valid]

    if kumpulan_gaji.empty:
        st.warning("Tiada data gaji yang sah untuk peringkat PhD.")
        return

    bins = [0, 4, 7, 8, np.inf]
    labels = [
        "RM2,000 dan kebawah",
        "RM2,001 - RM3,000",
        "RM3,001 - RM4,000",
        "RM4,001 dan keatas"
    ]
    gaji_bins = pd.cut(kumpulan_gaji, bins=bins, labels=labels, right=True)
    gaji_counts = gaji_bins.value_counts().reindex(labels, fill_value=0)

    gaji_df = pd.DataFrame({
        "Kategori Gaji": gaji_counts.index,
        "Bilangan Graduan": gaji_counts.values
    })

    fig = px.pie(
        gaji_df, 
        names="Kategori Gaji", 
        values="Bilangan Graduan", 
        category_orders={"Kategori Gaji": labels},
        hole=0.45,
    )
    fig.update_traces(
        textposition='inside',
        textinfo='percent'
    )

    fig.add_annotation(
        text="PhD",
        x=0.5, y=0.5,
        font_size=22,
        font_color="black",
        showarrow=False
    )
    fig.update_layout(
        width=250, height=230,
        legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", yanchor="bottom"),
        showlegend=False,
        margin=dict(t=2, b=2, l=2, r=2)
    )
    st.plotly_chart(fig, use_container_width=True)

def gaji_ikut_kumpulan_donut_diploma(df_filtered_year):
    donut_df = df_filtered_year[df_filtered_year["e_peringkat_label"] == "Diploma"]
    if "e_44_kumpulan" not in donut_df.columns or donut_df.empty:
        st.warning("Tiada data gaji untuk peringkat Diploma.")
        return

    kumpulan_gaji = pd.to_numeric(donut_df["e_44_kumpulan"], errors='coerce')
    mask_valid = ~kumpulan_gaji.isna() & (kumpulan_gaji != -2)
    kumpulan_gaji = kumpulan_gaji[mask_valid]

    if kumpulan_gaji.empty:
        st.warning("Tiada data gaji yang sah untuk peringkat Diploma.")
        return

    bins = [0, 4, 7, 8, np.inf]
    labels = [
        "RM2,000 dan kebawah",
        "RM2,001 - RM3,000",
        "RM3,001 - RM4,000",
        "RM4,001 dan keatas"
    ]
    gaji_bins = pd.cut(kumpulan_gaji, bins=bins, labels=labels, right=True)
    gaji_counts = gaji_bins.value_counts().reindex(labels, fill_value=0)

    gaji_df = pd.DataFrame({
        "Kategori Gaji": gaji_counts.index,
        "Bilangan Graduan": gaji_counts.values
    })

    fig = px.pie(
        gaji_df, 
        names="Kategori Gaji", 
        values="Bilangan Graduan", 
        category_orders={"Kategori Gaji": labels},
        hole=0.45,
    )
    fig.update_traces(
        textposition='inside',
        textinfo='percent'
    )

    fig.add_annotation(
        text="Diploma",
        x=0.5, y=0.5,
        font_size=20,
        font_color="black",
        showarrow=False
    )
    fig.update_layout(
        width=250, height=230,
        legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", yanchor="top"),
        showlegend=False,
        margin=dict(t=2, b=2, l=2, r=2)
    )
    st.plotly_chart(fig, use_container_width=True)

def gaji_ikut_kumpulan_donut_degree(df_filtered_year):
    donut_df = df_filtered_year[df_filtered_year["e_peringkat_label"] == "Sarjana Muda"]
    if "e_44_kumpulan" not in donut_df.columns or donut_df.empty:
        st.warning("Tiada data gaji untuk peringkat Sarjana Muda.")
        return

    kumpulan_gaji = pd.to_numeric(donut_df["e_44_kumpulan"], errors='coerce')
    mask_valid = ~kumpulan_gaji.isna() & (kumpulan_gaji != -2)
    kumpulan_gaji = kumpulan_gaji[mask_valid]

    if kumpulan_gaji.empty:
        st.warning("Tiada data gaji yang sah untuk peringkat Sarjana Muda.")
        return

    bins = [0, 4, 7, 8, np.inf]
    labels = [
        "RM2,000 dan kebawah",
        "RM2,001 - RM3,000",
        "RM3,001 - RM4,000",
        "RM4,001 dan keatas"
    ]
    gaji_bins = pd.cut(kumpulan_gaji, bins=bins, labels=labels, right=True)
    gaji_counts = gaji_bins.value_counts().reindex(labels, fill_value=0)

    gaji_df = pd.DataFrame({
        "Kategori Gaji": gaji_counts.index,
        "Bilangan Graduan": gaji_counts.values
    })

    fig = px.pie(
        gaji_df, 
        names="Kategori Gaji", 
        values="Bilangan Graduan", 
        category_orders={"Kategori Gaji": labels},
        hole=0.45,
    )
    fig.update_traces(
        textposition='inside',
        textinfo='percent'
    )

    fig.add_annotation(
        text="Sarjana<br>Muda",
        x=0.5, y=0.5,
        font_size=15,
        font_color="black",
        showarrow=False
    )
    fig.update_layout(
        width=250, height=230,
        legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", yanchor="top"),
        showlegend=False,
        margin=dict(t=2, b=2, l=2, r=2)
    )
    st.plotly_chart(fig, use_container_width=True)

def gaji_ikut_kumpulan_donut_master(df_filtered_year):
    donut_df = df_filtered_year[df_filtered_year["e_peringkat_label"] == "Sarjana"]
    if "e_44_kumpulan" not in donut_df.columns or donut_df.empty:
        st.warning("Tiada data gaji untuk peringkat Sarjana.")
        return

    kumpulan_gaji = pd.to_numeric(donut_df["e_44_kumpulan"], errors='coerce')
    mask_valid = ~kumpulan_gaji.isna() & (kumpulan_gaji != -2)
    kumpulan_gaji = kumpulan_gaji[mask_valid]

    if kumpulan_gaji.empty:
        st.warning("Tiada data gaji yang sah untuk peringkat Sarjana.")
        return

    bins = [0, 4, 7, 8, np.inf]
    labels = [
        "RM2,000 dan kebawah",
        "RM2,001 - RM3,000",
        "RM3,001 - RM4,000",
        "RM4,001 dan keatas"
    ]
    gaji_bins = pd.cut(kumpulan_gaji, bins=bins, labels=labels, right=True)
    gaji_counts = gaji_bins.value_counts().reindex(labels, fill_value=0)

    gaji_df = pd.DataFrame({
        "Kategori Gaji": gaji_counts.index,
        "Bilangan Graduan": gaji_counts.values
    })

    fig = px.pie(
        gaji_df, 
        names="Kategori Gaji", 
        values="Bilangan Graduan", 
        category_orders={"Kategori Gaji": labels},
        hole=0.45,
    )
    fig.update_traces(
        textposition='inside',
        textinfo='percent'
    )

    fig.add_annotation(
        text="Sarjana",
        x=0.5, y=0.5,
        font_size=20,
        font_color="black",
        showarrow=False
    )
    fig.update_layout(
        width=250, height=230,
        legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", yanchor="top"),
        showlegend=False,
        margin=dict(t=2, b=2, l=2, r=2)
    )
    st.plotly_chart(fig, use_container_width=True)

def fakulti_gm_tertinggi(df_filtered_year):
    valid_df = df_filtered_year[df_filtered_year["e_status_label"] != "Tiada Maklumat"]
    if valid_df.empty or "e_fakulti_label" not in valid_df.columns:
        st.warning("Tiada data fakulti yang sah.")
        return
    group = valid_df.groupby("e_fakulti_label")
    gm_per_faculty = (
        (group.size() - group["e_status_label"].apply(lambda x: (x == "Belum Bekerja").sum()))
        / group.size() * 100
    )
    gm_per_faculty = gm_per_faculty.dropna()
    if not gm_per_faculty.empty:
        fakulti_tertinggi = gm_per_faculty.idxmax()
        nilai_gm = gm_per_faculty.max()
        st.metric(
            label="Fakulti dengan GM Tertinggi",
            value=fakulti_tertinggi,
            delta=f"{nilai_gm:.1f}%",
            help="Fakulti dengan Graduate Marketability (GM) tertinggi"
        )
    else:
        st.warning("Tiada data GM yang sah untuk mana-mana fakulti.")

def fakulti_ge_tertinggi(df_filtered_year):
    if df_filtered_year.empty or "e_fakulti_label" not in df_filtered_year.columns:
        st.warning("Tiada data fakulti yang sah.")
        return

    all_fakulti = df_filtered_year["e_fakulti_label"].dropna().unique()
    records = []

    for fakulti in all_fakulti:
        fak_df = df_filtered_year[df_filtered_year["e_fakulti_label"] == fakulti]

        bekerja = (fak_df["e_status_label"] == "Bekerja").sum()
        belum_bekerja = (fak_df["e_status_label"] == "Belum Bekerja").sum()
        luar_tenaga_buruh = fak_df[
            (fak_df["e_status"] == 5) & 
            (fak_df["e_54"] != 5) & 
            (fak_df["e_54"] != 34)
        ]["e_54"].count()

        total_ge = bekerja + belum_bekerja - luar_tenaga_buruh
        percent_ge = (bekerja / total_ge * 100) if total_ge > 0 else 0

        records.append({
            "fakulti": fakulti,
            "GE": percent_ge
        })

    df_ge = pd.DataFrame(records)
    df_ge = df_ge.dropna(subset=["GE"])
    if not df_ge.empty:
        fakulti_tertinggi = df_ge.loc[df_ge["GE"].idxmax(), "fakulti"]
        ge_tertinggi = df_ge["GE"].max()
        st.metric(
            label="Fakulti dengan GE Tertinggi",
            value=fakulti_tertinggi,
            delta=f"{ge_tertinggi:.1f}%",
            help="Fakulti dengan peratusan Kadar Bekerja Graduan (GE) tertinggi"
        )
    else:
        st.warning("Tiada data GE yang sah untuk mana-mana fakulti.")

def fakulti_gm_atas_overall(df_filtered_year):
    valid_df = df_filtered_year[df_filtered_year["e_status_label"] != "Tiada Maklumat"]
    if valid_df.empty or "e_fakulti_label" not in valid_df.columns:
        st.warning("Tiada data fakulti yang sah.")
        return

    total_responden = valid_df.shape[0]
    total_belum_bekerja = (valid_df["e_status_label"] == "Belum Bekerja").sum()
    overall_gm = ((total_responden - total_belum_bekerja) / total_responden) * 100 if total_responden > 0 else 0

    group = valid_df.groupby("e_fakulti_label")
    gm_per_fakulti = (
        (group.size() - group["e_status_label"].apply(lambda x: (x == "Belum Bekerja").sum()))
        / group.size() * 100
    ).dropna()

    num_above = (gm_per_fakulti > overall_gm).sum()

    st.metric(
        label="Bilangan Fakulti GM Melebihi Purata",
        value=num_above,
        delta=f"Purata GM UM: {overall_gm:.1f}%",
        help="Bilangan fakulti yang mempunyai Kadar Kebolehpasaran Graduan (GM) lebih tinggi dari purata keseluruhan."
    )

def fakulti_ge_atas_overall(df_filtered_year):
    if df_filtered_year.empty or "e_fakulti_label" not in df_filtered_year.columns:
        st.warning("Tiada data fakulti yang sah.")
        return

    bekerja = (df_filtered_year["e_status_label"] == "Bekerja").sum()
    belum_bekerja = (df_filtered_year["e_status_label"] == "Belum Bekerja").sum()
    luar_tenaga_buruh = df_filtered_year[
        (df_filtered_year["e_status"] == 5) & 
        (df_filtered_year["e_54"] != 5) & 
        (df_filtered_year["e_54"] != 34)
    ]["e_54"].count()
    total_ge = bekerja + belum_bekerja - luar_tenaga_buruh
    overall_ge = (bekerja / total_ge * 100) if total_ge > 0 else 0

    group = df_filtered_year.groupby("e_fakulti_label")
    ge_per_fakulti = []
    for fakulti, fak_df in group:
        bekerja_f = (fak_df["e_status_label"] == "Bekerja").sum()
        belum_bekerja_f = (fak_df["e_status_label"] == "Belum Bekerja").sum()
        luar_tenaga_buruh_f = fak_df[
            (fak_df["e_status"] == 5) & 
            (fak_df["e_54"] != 5) & 
            (fak_df["e_54"] != 34)
        ]["e_54"].count()
        total_ge_f = bekerja_f + belum_bekerja_f - luar_tenaga_buruh_f
        ge_f = (bekerja_f / total_ge_f * 100) if total_ge_f > 0 else None
        if ge_f is not None:
            ge_per_fakulti.append((fakulti, ge_f))
    fakulti_above = [f for f, ge in ge_per_fakulti if ge > overall_ge]
    num_above = len(fakulti_above)
    st.metric(
        label="Bilangan Fakulti GE Melebihi Purata",
        value=num_above,
        delta=f"Purata GE UM: {overall_ge:.1f}%",
        help="Fakulti: " + ", ".join(fakulti_above) if fakulti_above else "Tiada"
    )

def purata_kadar_respons(df_filtered_year):
    if df_filtered_year.empty or "e_statusPenyertaan" not in df_filtered_year.columns:
        st.warning("Tiada data kadar respons.")
        return
    total = df_filtered_year["e_statusPenyertaan"].notna().sum()
    responded = (df_filtered_year["e_statusPenyertaan"] == 1).sum()
    purata = (responded / total * 100) if total > 0 else 0
    st.metric(
        label="Purata Kadar Respons (Keseluruhan)",
        value=f"{purata:.1f}%",
        help="Purata kadar respons keseluruhan untuk semua fakulti."
    )

def target_kadar_respons(df_filtered_year, target=90):
    if df_filtered_year.empty or "e_statusPenyertaan" not in df_filtered_year.columns:
        st.warning("Tiada data kadar respons.")
        return
    total = df_filtered_year["e_statusPenyertaan"].notna().sum()
    responded = (df_filtered_year["e_statusPenyertaan"] == 1).sum()
    purata = (responded / total * 100) if total > 0 else 0
    tercapai = purata >= target
    st.metric(
        label=f"Capai Sasaran Respons >{target}%",
        value="Tercapai" if tercapai else "Belum Tercapai",
        delta=f"{purata:.1f}%",
        help=f"Purata respons adalah {purata:.1f}% (Sasaran: >{target}%)"
    )

def fakulti_highest_kadar_respons(df_filtered_year):
    if df_filtered_year.empty or "e_fakulti_label" not in df_filtered_year.columns or "e_statusPenyertaan" not in df_filtered_year.columns:
        st.warning("Tiada data kadar respons.")
        return
    group = df_filtered_year.groupby("e_fakulti_label")
    records = []
    for fakulti, fak_df in group:
        total = fak_df["e_statusPenyertaan"].notna().sum()
        responded = (fak_df["e_statusPenyertaan"] == 1).sum()
        kadar = (responded / total * 100) if total > 0 else 0
        records.append((fakulti, kadar))
    if not records:
        st.warning("Tiada data fakulti.")
        return
    fakulti_max, kadar_max = max(records, key=lambda x: x[1])
    st.metric(
        label="Fakulti Kadar Respons Tertinggi",
        value=fakulti_max,
        delta=f"{kadar_max:.1f}%",
        help="Fakulti dengan kadar respons tertinggi."
    )

def fakulti_lowest_kadar_respons(df_filtered_year):
    if df_filtered_year.empty or "e_fakulti_label" not in df_filtered_year.columns or "e_statusPenyertaan" not in df_filtered_year.columns:
        st.warning("Tiada data kadar respons.")
        return
    group = df_filtered_year.groupby("e_fakulti_label")
    records = []
    for fakulti, fak_df in group:
        total = fak_df["e_statusPenyertaan"].notna().sum()
        responded = (fak_df["e_statusPenyertaan"] == 1).sum()
        kadar = (responded / total * 100) if total > 0 else 0
        records.append((fakulti, kadar))
    if not records:
        st.warning("Tiada data fakulti.")
        return
    fakulti_min, kadar_min = min(records, key=lambda x: x[1])
    st.metric(
        label="Fakulti Kadar Respons Terendah",
        value=fakulti_min,
        delta=f"{kadar_min:.1f}%",
        help="Fakulti dengan kadar respons terendah."
    )

def table_status_pekerjaan():
    if not df_filtered_year.empty and "e_status" in df_filtered_year.columns:
        status_df = df_filtered_year[df_filtered_year["e_status"].isin([1,2,3,4,5])]
        grouped = (
            status_df.groupby("e_status")
            .size()
            .reset_index(name="Bilangan Graduan")
            .sort_values("e_status")
        )
        total = grouped["Bilangan Graduan"].sum()
        grouped["Peratus (%)"] = grouped["Bilangan Graduan"] / total * 100
        grouped["Peratus (%)"] = grouped["Peratus (%)"].round(2)

        status_kerja_map = {
            1: "Bekerja",
            2: "Melanjutkan Pengajian",
            3: "Meningkatkan kemahiran",
            4: "Menunggu penempatan pekerjaan",
            5: "Belum Bekerja",
        }
        grouped["Status Pekerjaan"] = grouped["e_status"].map(status_kerja_map)
        grouped = grouped[["Status Pekerjaan", "Bilangan Graduan", "Peratus (%)"]]

        st.markdown("#### Jadual Status Pekerjaan")
        st.dataframe(grouped, hide_index=True, use_container_width=True)

def kategori_ge(df_filtered_year):
    all_fakulti = [
        "API", "APM", "FAB", "FBL", "FF", "FK", "EDU", "FOD", "FPE", "FOM",
        "FS", "FSKTM", "FSSS", "FSK", "FSSE", "FUU", "AEI", "IAS", "INPUMA", "UMCCED"
    ]

    required_cols = ["e_status_label", "e_status", "e_54", "e_fakulti_label"]
    if not all(col in df_filtered_year.columns for col in required_cols):
        st.warning("Kolum yang diperlukan tidak lengkap dalam data.")
        return

    records = []
    for fakulti in all_fakulti:
        fak_df = df_filtered_year[df_filtered_year["e_fakulti_label"] == fakulti]
        total_graduan = fak_df.shape[0]
        bekerja = fak_df[fak_df["e_status_label"] == "Bekerja"]["e_status_label"].count()
        tidak_bekerja = fak_df[fak_df["e_status_label"] == "Belum Bekerja"]["e_status_label"].count()
        luar_tenaga_buruh = fak_df[
            (fak_df["e_status"] == 5) &
            (fak_df["e_54"] != 5) &
            (fak_df["e_54"] != 34)
        ]["e_54"].count()
        total_ge = bekerja + tidak_bekerja - luar_tenaga_buruh
        percent_ge = (bekerja / total_ge * 100) if total_ge > 0 else 0

        if total_graduan < 200:
            kategori = "Kategori 1 (<200)"
        elif 200 <= total_graduan <= 700:
            kategori = "Kategori 2 (201-700)"
        else:
            kategori = "Kategori 3 (>701)"

        records.append({
            "Fakulti": fakulti,
            "GE (%)": round(percent_ge, 1),
            "Kategori": kategori,
            "Bilangan Graduan": total_graduan
        })

    kategori_order = ["Kategori 1 (<200)", "Kategori 2 (201-700)", "Kategori 3 (>701)"]
    df_chart = pd.DataFrame(records)
    df_chart["Kategori"] = pd.Categorical(df_chart["Kategori"], categories=kategori_order, ordered=True)
    df_chart = df_chart.sort_values(["Kategori", "Fakulti"])

    st.markdown("##### Kadar GE Mengikut Kategori Bilangan Graduan")

    fig = px.bar(
        df_chart,
        x="Fakulti",
        y="GE (%)",
        color="Kategori",
        text="GE (%)",
        labels={
            "GE (%)": "GE (%)",
            "Fakulti": "Fakulti",
            "Kategori": "Kategori Bilangan Graduan"
        },
        category_orders={"Kategori": kategori_order, "Fakulti": df_chart["Fakulti"].tolist()},
        height=500,
        width=max(1100, 55 * len(all_fakulti))
    )
    fig.update_traces(texttemplate='%{text:.1f}', textposition='inside')
    fig.update_layout(
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1,
            xanchor="center",
            x=0.15
        ),
        xaxis_tickangle=-40,
        legend_title="Kategori Bilangan Graduan",
        xaxis_title=None,
        yaxis_title=None,
        margin=dict(l=40, r=40, t=40, b=40),
        uniformtext_minsize=8,
        uniformtext_mode='hide'
    )
    st.plotly_chart(fig, use_container_width=True)

    # st.markdown("#### Jadual GE Mengikut Kategori Bilangan Graduan")
    # st.dataframe(df_chart, hide_index=True, use_container_width=True)

def data_graduan():
    st.markdown("### Data Graduan")
    st.dataframe(df_filtered_year)

# --- DASHBOARD LAYOUT STARTS HERE ---
topdash = st.columns((1.2,1))
table_status_pekerjaan()
kategori_ge(df_filtered_year)
PTj1 = st.columns((3.5,1))
PTj2 = st.columns((1,3.5))
st.markdown("""
<div style="margin-top: 8px; font-size:18px; font-weight:bold;">
Pendapatan Bulanan Mengikut Peringkat Pengajian
</div>
<div style="display: flex; align-items: center; gap: 18px;">
  <span style="font-weight: bold;">Kategori:</span>
  <span style="background: #0068C9; border-radius:4px; width: 14px; height: 14px; display: inline-block; margin-right:6px;"></span>
  <span style="font-size:12px; vertical-align: middle;">RM2,000 dan kebawah</span>
  <span style="background: #83C9FF; border-radius:4px; width: 14px; height: 14px; display: inline-block; margin-left:14px; margin-right:6px;"></span>
  <span style="font-size:12px; vertical-align: middle;">RM2,001 - RM3,000</span>
  <span style="background: #FF2B2B; border-radius:4px; width: 14px; height: 14px; display: inline-block; margin-left:14px; margin-right:6px;"></span>
  <span style="font-size:12px; vertical-align: middle;">RM3,001 - RM4,000</span>
  <span style="background: #FFABAB; border-radius:4px; width: 14px; height: 14px; display: inline-block; margin-left:14px; margin-right:6px;"></span>
  <span style="font-size:12px; vertical-align: middle;">RM4,001 dan keatas</span>
</div>
""", unsafe_allow_html=True)
donut = st.columns((1,1,1,1))
PTj3 = st.columns((1,1))

with topdash[0]:
    ge_gm_line_tahun(df)
    table_gm_tahun(df)
with topdash[1]:
    ge_gm_keseluruhan(df_filtered_year)

with PTj1[0]:
    graduate_employability_ikut_ptj(df_filtered_year)
with PTj1[1]:
    st.write("")
    fakulti_gm_tertinggi(df_filtered_year)
    fakulti_ge_tertinggi(df_filtered_year)
    fakulti_gm_atas_overall(df_filtered_year)
    fakulti_ge_atas_overall(df_filtered_year)

with PTj2[0]:
    st.write("")
    purata_kadar_respons(df_filtered_year)
    target_kadar_respons(df_filtered_year)
    fakulti_highest_kadar_respons(df_filtered_year)
    fakulti_lowest_kadar_respons(df_filtered_year)
with PTj2[1]:
    kadar_respons_ikut_ptj(df_filtered_year)

with donut[0]:
    gaji_ikut_kumpulan_donut_phd(df_filtered_year)
with donut[1]:
    gaji_ikut_kumpulan_donut_master(df_filtered_year)
with donut[2]:
    gaji_ikut_kumpulan_donut_degree(df_filtered_year)
with donut[3]:
    gaji_ikut_kumpulan_donut_diploma(df_filtered_year)

with PTj3[0]:
    bekerja_dalam_bidang_ikut_ptj(df_filtered_year)
with PTj3[1]:
    kemahiran_kerja(df_filtered_year)