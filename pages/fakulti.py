import os
import re
import pandas as pd
import streamlit as st
import numpy as np
import plotly.express as px

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except Exception:
    DUCKDB_AVAILABLE = False

st.set_page_config(
    page_title="Dashboard SKPG Fakulti",
    page_icon="lencana.jpg",
    layout="wide"
)

script_dir = os.path.dirname(os.path.abspath(__file__))
data_folder = os.path.join(script_dir, "Data SKPG")
os.makedirs(data_folder, exist_ok=True)

xlsx_pattern = re.compile(r"Data SKPG (\d{4})\.xlsx")

def ensure_parquet_from_excel(xlsx_path: str, parquet_path: str, sheet: str = "DATASET") -> None:
    """
    If parquet_path is missing or older than xlsx_path, convert using DuckDB's Excel extension.
    """
    if not DUCKDB_AVAILABLE:
        return
    if not os.path.exists(xlsx_path):
        return

    needs_convert = True
    if os.path.exists(parquet_path):
        needs_convert = os.path.getmtime(parquet_path) < os.path.getmtime(xlsx_path)
    if not needs_convert:
        return

    con = duckdb.connect()
    try:
        con.execute("INSTALL excel; LOAD excel;")
        con.execute(f"""
            COPY (
                SELECT * FROM read_excel('{xlsx_path}', sheet='{sheet}')
            )
            TO '{parquet_path}' (FORMAT PARQUET);
        """)
    finally:
        con.close()

def build_year_maps(folder: str):
    """
    Build year->xlsx and year->parquet maps. If DuckDB is available, create/refresh Parquet.
    """
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
    st.warning("Tiada data dijumpai untuk tahun yang dipilih.")
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
    "-2" : "Tiada Maklumat",
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
    "5" : "Bekerja  dengan Keluarga",
    "6" : "Majikan",
    "7" : "Pekerja Kerajaan",
    "8" : "Pekerja Swasta (Termasuk NGO)",
    "9" : "Pekerja (Kerajaan/Swasta/Pekerja Keluarga dengan upah/gaji)",
    "10" : "Pekerja (Kerajaan/Swasta)",
    "40" : "Freelance",
    "46" : "Usahawan",
    "47" : "Bekerja Sendiri (e+p-hailing)",
    "51" : "Bekerja  dengan Keluarga (upah/gaji)",
    "52" : "Bekerja dengan Keluarga (tiada upah/gaji)",
}
kumpulan_pekerjaan_map = {
    "-2" : "Tidak Berkenaan",
    "1" : "Pengurus",
    "2" : "Profesional",
    "3" : "Juruteknik dan Profesional Bersekutu",
    "4" : "Pekerja Sokongan Perkeranian",
    "5" : "Pekerja Perkhidmatan dan Jualan",
    "6" : "Pekerja Mahir Pertanian, Perhutanan, Penternakan, dan Perikanan",
    "7" : "Pekerja Kemahiran dan Pekerja Pertukangan yang Berkaitan",
    "8" : "Operator Mesin dan Loji, dan Pemasang",
    "9" : "Pekerja Asas",
    "10" : "Angkatan Tentera",
}
bekerja_dalam_bidang_map = {
    "-2" : "Tidak Berkenaan",
    "-1" : "Tidak Dinyatakan",
    "1" : "Ya",
    "2" : "Tidak",
}

df = df.copy()

df["e_warganegara_label"] = df["e_warganegara"].astype(str).map(warganegara_map)
df["e_40_label"] = df["e_40"].astype(str).map(status_pekerjaan_map)
if "e_status_GE2024" in df.columns:
    df["e_status_GE2024_label"] = df["e_status_GE2024"].astype(str).map(status_kerjage_map)
df["e_status_label"] = df["e_status"].astype(str).map(status_kerja_map)
df["e_statusPenyertaan_label"] = df["e_statusPenyertaan"].astype(str).map(status_penyertaan_map)
df["e_54_label"] = df["e_54"].astype(str).map(sebab_tidak_bekerja_map)
df["e_peringkat_label"] = df["e_peringkat"].astype(str).map(peringkat_pengajian_map)
df["e_fakulti_label"] = df["e_fakulti"].astype(str).map(fakulti_map)
df["e_43_label"] = df["e_43"].astype(str).map(taraf_pekerjaan_map)
df["e_45_label"] = df["e_45"].astype(str).map(sektor_pekerjaan_map)
df["e_41_a_label"] = df["e_41_a"].astype(str).map(kumpulan_pekerjaan_map)
df["e_50_b_label"] = df["e_50_b"].astype(str).map(bekerja_dalam_bidang_map)

warganegara_label_list = [warganegara_map["1"], warganegara_map["2"]]

# with filter_col[5]:
#     selected_status_bekerja = st.multiselect(
#         "Pilih Status Bekerja:",
#         options=status_bekerja_list,
#         help="Klik untuk pilih satu atau beberapa status bekerja. Dibiarkan kosong untuk semua."
#     )
#     if not selected_status_bekerja:
#         tapis_bekerja = tapis_program
#         selected_status_bekerja = status_bekerja_list
#     else:
#         tapis_bekerja = tapis_program[tapis_program["e_status_label"].isin(selected_status_bekerja)]


# --- FILTERS UI AT TOP ---
filter_col = st.columns((0.7,1,1,1,0.7))

with filter_col[0]:
    selected_years = st.multiselect(
        "Pilih Tahun Data SKPG:",
        options=available_years,
        help="Pilih satu, beberapa tahun, atau kosongkan untuk semua tahun."
    )
    if not selected_years:
        tapis_tahun = df
        selected_years = available_years
    else:
        tapis_tahun = df[df['SKPG_Tahun'].isin(selected_years)]

fakulti_list = sorted(tapis_tahun["e_fakulti"].dropna().unique())

with filter_col[1]:
    selected_fakultis = st.multiselect(
        "Pilih Fakulti:",
        options=fakulti_list,
        help="Klik untuk pilih satu atau beberapa fakulti. Dibiarkan kosong untuk semua."
    )
    if not selected_fakultis:
        tapis_fakulti = tapis_tahun
        selected_fakultis = fakulti_list
    else:
        tapis_fakulti = df[df["e_fakulti"].isin(selected_fakultis)]

peringkat_pengajian_list = sorted(tapis_fakulti["e_peringkat_label"].dropna().unique())

with filter_col[2]:
    selected_peringkat_pengajian = st.multiselect(
        "Pilih Peringkat Pengajian:",
        options=peringkat_pengajian_list,
        help="Klik untuk pilih satu atau beberapa peringkat pengajian. Dibiarkan kosong untuk semua."
    )
    if not selected_peringkat_pengajian:
        tapis_peringkat = tapis_fakulti
        selected_peringkat_pengajian = peringkat_pengajian_list
    else:
        tapis_peringkat = tapis_fakulti[tapis_fakulti["e_peringkat_label"].isin(selected_peringkat_pengajian)]

program_list = sorted(tapis_peringkat["e_program"].dropna().unique())

with filter_col[3]:
    selected_programs = st.multiselect(
        "Pilih Program:",
        options=program_list,
        help="Klik untuk pilih satu atau beberapa program. Dibiarkan kosong untuk semua."
    )
    if not selected_programs:
        tapis_program = tapis_peringkat
        selected_programs = program_list
    else:
        tapis_program = tapis_peringkat[tapis_peringkat["e_program"].isin(selected_programs)]

status_bekerja_list = sorted(tapis_program["e_status_label"].dropna().unique())

with filter_col[4]:
    selected_warganegara = st.selectbox(
        "Pilih Warganegara:",
        options=["Semua"] + warganegara_label_list,
        help="Klik untuk pilih satu atau beberapa status warganegara. Dibiarkan kosong untuk semua."
    )
    if selected_warganegara == "Semua":
        selected_warganegara_tapis = warganegara_label_list
    else:
        selected_warganegara_tapis = [selected_warganegara]

# --- FILTER DATA ---
df_filtered_year = df[df['SKPG_Tahun'].isin(selected_years)]
filtered_for_program = df_filtered_year[df_filtered_year["e_fakulti"].isin(selected_fakultis)]

filtered_df = df_filtered_year[
    df_filtered_year["e_fakulti"].isin(selected_fakultis) &
    df_filtered_year["e_warganegara_label"].isin(selected_warganegara_tapis) &
    df_filtered_year["e_peringkat_label"].isin(selected_peringkat_pengajian) &
    df_filtered_year["e_program"].isin(selected_programs)
    # df_filtered_year["e_status_label"].isin(selected_status_bekerja) 
]

# --- DASHBOARD METRICS AND CHARTS ---
def dashboard_title():
    if selected_fakultis and len(selected_fakultis) == 1:
        st.markdown(
            f"<div style='font-size:28px; font-weight:bold; margin-bottom: 12px;'>Dashboard SKPG Bagi {selected_fakultis[0]}</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            "<div style='font-size:28px; font-weight:bold; margin-bottom: 12px;'>Dashboard SKPG Universiti Malaya</div>",
            unsafe_allow_html=True
        )

def jumlah_keseluruhan_graduan():
    total_graduan = ringkasan_total_df.shape[0]
    st.metric(
        label="Jumlah Graduan",
        value=f"{total_graduan}",
        delta=""
    )

def peratusan_responden():
    if "e_statusPenyertaan_label" in ringkasan_total_df.columns:
        total_responden = ringkasan_total_df["e_statusPenyertaan_label"].count()
        total_lengkap = ringkasan_total_df[ringkasan_total_df["e_statusPenyertaan_label"] == "Sertai"]["e_statusPenyertaan_label"].count()
        if total_responden > 0:
            peratusan = (total_lengkap / total_responden) * 100
            st.metric(
                label="Responden",
                value=f"{peratusan:.1f}%",
                delta=f"{total_lengkap}"
            )
        else:
            st.metric(
                label="Peratusan Responden",
                value="Error",
                delta=""
            )

def kadar_kebolehpasaran():
    if "e_status_GE2024_label" in ringkasan_total_df.columns:
        total_graduan = ringkasan_total_df[ringkasan_total_df["e_status_GE2024_label"] != "Tidak Berkenaan"]["e_status_GE2024_label"].count()
        total_bekerja = ringkasan_total_df[ringkasan_total_df["e_status_GE2024_label"] == "Bekerja"]["e_status_GE2024_label"].count()
        st.metric(
            label="Kadar GE",
            value=f"{(total_bekerja / total_graduan * 100) if total_graduan > 0 else 0:.1f}%",
            delta=""
        )

def total_program():
    if "e_program" in ringkasan_total_df.columns:
        total_programs = ringkasan_total_df["e_program"].nunique()
        st.metric(
            label="Jumlah Program",
            value=f"{total_programs}",
            delta=""
        )

def jadual_status_kerja():
    if not filtered_df.empty and "e_status_label" in filtered_df.columns:
        valid_df = filtered_df[filtered_df["e_status_label"].str.lower() != "tiada maklumat"]
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
    if not filtered_df.empty and "e_peringkat_label" in filtered_df.columns:
        peringkat_counts = filtered_df["e_peringkat_label"].value_counts().reset_index()
        peringkat_counts.columns = ["Peringkat Pengajian", "Bilangan Graduan"]
        st.markdown("### Jadual Peringkat Pengajian Graduan")
        st.dataframe(peringkat_counts, hide_index=True)

def plot_gaji_piechart():
    if "e_44_2" in filtered_df.columns:
        def clean_gaji(x):
            if pd.isna(x):
                return None
            s = str(x).lower().replace("rm", "").replace(",", "").replace(" ", "").strip()
            try:
                return float(s)
            except Exception:
                return None

        gaji_value = filtered_df["e_44_2"].apply(clean_gaji)
        def group_gaji(value):
            if value is None:
                return "Tiada Maklumat"
            elif value < 2000:
                return "Bawah RM2,000"
            elif 2000 <= value < 3000:
                return "RM2,000 - RM2,999"
            elif 3000 <= value < 4000:
                return "RM3,000 - RM3,999"
            elif value >= 4000:
                return "RM4,000 dan keatas"
            else:
                return "Tiada Maklumat"

        categories = ["Bawah RM2,000", "RM2,000 - RM2,999", "RM3,000 - RM3,999", "RM4,000 dan keatas", "Tiada Maklumat"]
        gaji_bins = gaji_value.apply(group_gaji)
        gaji_counts = gaji_bins.value_counts().reindex(categories, fill_value=0)
        gaji_df = pd.DataFrame({
            "Kategori Gaji": gaji_counts.index,
            "Bilangan Graduan": gaji_counts.values
        })
        gaji_df["angle"] = gaji_df["Bilangan Graduan"] / gaji_df["Bilangan Graduan"].sum() * 2 * np.pi
        gaji_df["color"] = gaji_df["Kategori Gaji"]
        st.markdown("##### Pendapatan Bulanan")
        fig = px.pie(
            gaji_df, 
            names="Kategori Gaji", 
            values="Bilangan Graduan", 
            category_orders={"Kategori Gaji": categories},
            hole=0,
        )
        fig.update_traces(
            textposition='inside',
            textinfo='percent',
            showlegend=True
        )
        fig.update_layout(
            width=350, height=330,
            legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", yanchor="top"),
            margin=dict(t=2, b=2, l=2, r=2)
        )
        st.plotly_chart(fig, use_container_width=True)

def plot_gaji():
    if "e_44_2" in filtered_df.columns:
        def clean_gaji(x):
            if pd.isna(x):
                return None
            s = str(x).lower().replace("rm", "").replace(",", "").replace(" ", "").strip()
            try:
                return float(s)
            except Exception:
                return None

        gaji_value = filtered_df["e_44_2"].apply(clean_gaji)
        def group_gaji(value):
            if value is None:
                return "Tiada Maklumat"
            elif value <= 2000:
                return "RM2,000 dan kebawah"
            elif 2000 < value <= 3000:
                return "RM2,001 - RM3,000"
            elif 3000 < value <= 5000:
                return "RM3,001 - RM5,000"
            elif 5000 < value <= 10000:
                return "RM5,001 - RM10,000"
            elif value > 10000:
                return "RM10,000 dan keatas"
            else:
                return "Tiada Maklumat"
        categories = ["RM2,000 dan kebawah", "RM2,001 - RM3,000", "RM3,001 - RM5,000", "RM5,001 - RM10,000", "RM10,000 dan keatas", "Tiada Maklumat"]
        gaji_bins = gaji_value.apply(group_gaji)
        gaji_counts = gaji_bins.value_counts().reindex(categories, fill_value=0)
        gaji_df = pd.DataFrame({
            "Kategori Gaji": gaji_counts.index,
            "Bilangan Graduan": gaji_counts.values
        })
        st.markdown("### Taburan Gaji")
        st.dataframe(gaji_df, hide_index=True)

def gaji_premium():
    if "e_44_2" in filtered_df.columns and "e_peringkat_label" in filtered_df.columns:
        def clean_gaji(x):
            if pd.isna(x):
                return None
            s = str(x).lower().replace("rm", "").replace(",", "").replace(" ", "").strip()
            try:
                return float(s)
            except Exception:
                return None
            
        gaji_hebat = filtered_df["e_44_2"].apply(clean_gaji)
        total = gaji_hebat.count()
        premium = gaji_hebat[gaji_hebat >= 4000].count()
        percent_premium = (premium / total * 100) if total > 0 else 0

        st.metric(
            label="Gaji Premium (>RM4000)",
            value=f"{percent_premium:.1f}%",
            delta=f"{premium}",
        )

def gaji_premium_kumpulan():
    if "e_44_kumpulan" in filtered_df.columns and "e_peringkat_label" in filtered_df.columns:
        gaji_premium = filtered_df[filtered_df["e_44_kumpulan"] != -2]["e_44_kumpulan"]
        total = gaji_premium.count()
        real_premium = gaji_premium[gaji_premium >= 11].count()
        percent_premium = (real_premium / total * 100) if total > 0 else 0

        st.metric(
            label="Gaji Premium (>RM4000)",
            value=f"{percent_premium:.1f}%",
            delta=f"{real_premium}",
        )

def graduate_employability():
    if "e_status_label" and "e_54" and "e_status" in filtered_df.columns:
        bekerja = filtered_df[filtered_df["e_status_label"] == "Bekerja"]["e_status_label"].count()
        tidak_bekerja = filtered_df[filtered_df["e_status_label"] == "Belum Bekerja"]["e_status_label"].count()
        
        luar_tenaga_buruh = filtered_df[(filtered_df["e_status"] == 5) & (filtered_df["e_54"] != 5) & (filtered_df["e_54"] != 34)]["e_54"].count()


        total_ge = bekerja + tidak_bekerja - luar_tenaga_buruh
        percent_ge = (bekerja / total_ge * 100) if total_ge > 0 else 0

        st.metric(
            label="Kadar Bekerja Graduan (GE)",
            value=f"{percent_ge:.1f}%",
            delta=f"{bekerja}",
        )

def graduate_marketability():
    if "e_status_label" in filtered_df.columns:
        responden = filtered_df[filtered_df["e_status_label"] != "Tiada Maklumat"]["e_status_label"].count()
        belum_bekerja = filtered_df[filtered_df["e_status_label"] == "Belum Bekerja"]["e_status_label"].count()
        gm = (responden - belum_bekerja) / responden * 100 if responden > 0 else 0

        st.metric(
            label="Kebolehpasaran Graduan (GM)",
            value=f"{gm:.1f}%",
            delta=f"{responden - belum_bekerja}",
        )

def plot_sebab_belum_kerja_piechart():
    if "e_54_label" in filtered_df.columns:
        sebab = (
            filtered_df["e_54_label"].value_counts().head(5).reset_index()
        )
        sebab.columns = ["Sebab Tidak Bekerja", "Bilangan Graduan"]

        def wrap_label(label, width=60):
            words = label.split()
            lines = []
            line = ""
            for word in words:
                if len(line) + len(word) + 1 > width:
                    lines.append(line)
                    line = word
                else:
                    if line:
                        line += " "
                    line += word
            lines.append(line)
            return "<br>".join(lines)

        sebab["Sebab Tidak Bekerja"] = sebab["Sebab Tidak Bekerja"].apply(lambda x: wrap_label(str(x), width=60))

        sebab["Peratus"] = (sebab["Bilangan Graduan"] / sebab["Bilangan Graduan"].sum()) * 100
        sebab["Label"] = sebab["Peratus"].round(1).astype(str) + "%"

        st.markdown("##### Sebab Tidak Bekerja")
        fig = px.pie(
            sebab,
            names="Sebab Tidak Bekerja",
            values="Bilangan Graduan",
            hole=0,
        )
        fig.update_traces(
            textinfo='percent',
            textposition='inside',
            showlegend=True
        )
        fig.update_layout(
            width=400,
            height=500,
            legend=dict(
                orientation="h",
                y=-0.2,
                x=0.5,
                xanchor="center",
                yanchor="top",
                font=dict(size=10)
            ),
            margin=dict(t=20, b=40, l=20, r=20)
        )
        st.plotly_chart(fig, use_container_width=True)

def histogram_sebab_tak_bekerja():
    if (not filtered_df.empty and "e_54_label" in filtered_df.columns):
        df_status = filtered_df[filtered_df["e_status"] == 5]
        grouped = df_status.groupby(["e_54_label"]).size().reset_index(name="Bilangan Graduan")
        grouped = grouped.sort_values("Bilangan Graduan", ascending=False)
        grouped["Peratus"] = grouped["Bilangan Graduan"] / grouped["Bilangan Graduan"].sum() * 100

        def truncate_label(label, width=40):
            return label if len(label) <= width else label[:width-3] + "..."

        grouped["e_54_label_wrapped"] = grouped["e_54_label"].apply(lambda x: truncate_label(str(x), width=40))
        category_order = grouped["e_54_label_wrapped"].tolist()
        st.markdown("##### Sebab Tidak Bekerja (%)")
        fig = px.bar(
            grouped,
            x="e_54_label_wrapped",
            y="Peratus",
            labels={
                "Peratus": "Peratus (%)",
                "e_54_label_wrapped": "Sebab Tidak Bekerja",
                "e_54_label": "Sebab Tidak Bekerja"
            },
            height=350,
            color="e_54_label_wrapped",
            color_discrete_sequence=px.colors.qualitative.Plotly,
            text=grouped["Peratus"].map("{:.1f}%".format),
            hover_data={"e_54_label": True, "Bilangan Graduan": True, "Peratus": True},
            category_orders={"e_54_label_wrapped": category_order}
        )
        fig.update_traces(textposition='outside')
        fig.update_layout(showlegend=False, xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

def histogram_kumpulan_pekerjaan():
    if (not filtered_df.empty and "e_41_a_label" in filtered_df.columns):
        filtered = filtered_df[(filtered_df["e_41_a_label"] != "Tidak Berkenaan") & (filtered_df["e_statusPenyertaan"] == 1)]
        grouped = filtered.groupby(["e_41_a_label"]).size().reset_index(name="Bilangan Graduan")
        grouped = grouped.sort_values("Bilangan Graduan", ascending=False)
        grouped["Peratus"] = grouped["Bilangan Graduan"] / grouped["Bilangan Graduan"].sum() * 100

        def truncate_label(label, width=40):
            return label if len(label) <= width else label[:width-3] + "..."

        grouped["e_41_a_label_wrapped"] = grouped["e_41_a_label"].apply(lambda x: truncate_label(str(x), width=40))
        category_order = grouped["e_41_a_label_wrapped"].tolist()
        st.markdown("##### Kumpulan Pekerjaan Graduan (%)")
        fig = px.bar(
            grouped,
            x="e_41_a_label_wrapped",
            y="Peratus",
            labels={
                "Peratus": "Peratus (%)",
                "e_41_a_label_wrapped": "Kumpulan Pekerjaan",
                "e_41_a_label": "Kumpulan Pekerjaan"
            },
            height=350,
            color="e_41_a_label_wrapped",
            color_discrete_sequence=px.colors.qualitative.Plotly,
            text=grouped["Peratus"].map("{:.1f}%".format),
            hover_data={"e_41_a_label": True, "Bilangan Graduan": True, "Peratus": True},
            category_orders={"e_41_a_label_wrapped": category_order}
        )
        fig.update_traces(textposition='outside')
        fig.update_layout(showlegend=False, xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)   

def histogram_taraf_pekerjaan():
    if (not filtered_df.empty and "e_43_label" in filtered_df.columns):
        filtered = filtered_df[(filtered_df["e_43_label"] != "Tidak Berkenaan") & (filtered_df["e_statusPenyertaan"] == 1)]
        grouped = filtered.groupby(["e_43_label"]).size().reset_index(name="Bilangan Graduan")
        grouped = grouped.sort_values("Bilangan Graduan", ascending=False)
        grouped["Peratus"] = grouped["Bilangan Graduan"] / grouped["Bilangan Graduan"].sum() * 100

        def truncate_label(label, width=40):
            return label if len(label) <= width else label[:width-3] + "..."

        grouped["e_43_label_wrapped"] = grouped["e_43_label"].apply(lambda x: truncate_label(str(x), width=40))
        category_order = grouped["e_43_label_wrapped"].tolist()
        st.markdown("##### Taraf Pekerjaan Graduan (%)")
        fig = px.bar(
            grouped,
            x="e_43_label_wrapped",
            y="Peratus",
            labels={
                "Peratus": "Peratus (%)",
                "e_43_label_wrapped": "Taraf Pekerjaan",
                "e_43_label": "Taraf Pekerjaan"
            },
            height=350,
            color="e_43_label_wrapped",
            color_discrete_sequence=px.colors.qualitative.Plotly,
            text=grouped["Peratus"].map("{:.1f}%".format),
            hover_data={"e_43_label": True, "Bilangan Graduan": True, "Peratus": True},
            category_orders={"e_43_label_wrapped": category_order}
        )
        fig.update_traces(textposition='outside')
        fig.update_layout(showlegend=False, xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

def histogram_sektor_pekerjaan():
    if (not filtered_df.empty and "e_45_label" in filtered_df.columns):
        filtered = filtered_df[(filtered_df["e_45_label"] != "Tidak Berkenaan") & (filtered_df["e_statusPenyertaan"] == 1)]
        grouped = filtered.groupby(["e_45_label"]).size().reset_index(name="Bilangan Graduan")
        grouped = grouped.sort_values("Bilangan Graduan", ascending=False)
        grouped["Peratus"] = grouped["Bilangan Graduan"] / grouped["Bilangan Graduan"].sum() * 100

        st.markdown("##### Sektor Pekerjaan Graduan (%)")

        def truncate_label(label, width=40):
            return label if len(label) <= width else label[:width-3] + "..."

        grouped["e_45_label_wrapped"] = grouped["e_45_label"].apply(lambda x: truncate_label(str(x), width=40))

        category_order = grouped["e_45_label_wrapped"].tolist()

        fig = px.bar(
            grouped,
            x="e_45_label_wrapped",
            y="Peratus",
            labels={
                "Peratus": "Peratus (%)",
                "e_45_label_wrapped": "Sektor Pekerjaan",
                "e_45_label": "Sektor Pekerjaan"
            },
            height=350,
            color="e_45_label",
            color_discrete_sequence=px.colors.qualitative.Plotly,
            text=grouped["Peratus"].map("{:.1f}%".format),
            hover_data={"e_45_label": True, "Bilangan Graduan": True, "Peratus": True},
            category_orders={"e_45_label_wrapped": category_order}
        )
        fig.update_traces(textposition='outside')
        fig.update_layout(showlegend=False, xaxis_title=None)
        st.plotly_chart(fig, use_container_width=True)

def plot_bekerja_dalam_bidang():
    if "e_50_b_label" in filtered_df.columns:
        bidang = (
            filtered_df[filtered_df["e_50_b_label"] != "Tidak Berkenaan"]["e_50_b_label"]
            .value_counts()
            .reset_index()
        )
        bidang.columns = ["Bekerja Dalam Bidang", "Bilangan Graduan"]

        bidang["Peratus"] = (bidang["Bilangan Graduan"] / bidang["Bilangan Graduan"].sum()) * 100
        bidang["Label"] = bidang["Peratus"].round(1).astype(str) + "%"

        st.markdown("##### Bekerja Dalam Bidang")
        fig = px.pie(
            bidang,
            names="Bekerja Dalam Bidang",
            values="Bilangan Graduan",
            hole=0,
            color="Bekerja Dalam Bidang",
            color_discrete_map={
                "Ya": "#0068C9",
                "Tidak": "#FF4B4B"
            }
        )
        fig.update_traces(
            textinfo='percent',
            textposition='inside',
            showlegend=True
        )
        fig.update_layout(
            width=350,
            height=350,
            legend=dict(
                orientation="h",
                y=-0.2,
                x=0.5,
                xanchor="center",
                yanchor="top",
                font=dict(size=10)
            ),
            margin=dict(t=20, b=40, l=20, r=20)
        )
        st.plotly_chart(fig, use_container_width=True)

def table_bekerja_dalam_bidang():
    if not filtered_df.empty and "e_50_b_label" in filtered_df.columns:
        filtered = filtered_df[filtered_df["e_50_b_label"] != "Tidak Berkenaan"]
        grouped = (
            filtered.groupby("e_50_b_label")
            .size()
            .reset_index(name="Bilangan Graduan")
            .sort_values("Bilangan Graduan", ascending=False)
        )
        total = grouped["Bilangan Graduan"].sum()
        grouped["Peratus (%)"] = grouped["Bilangan Graduan"] / total * 100
        grouped["Peratus (%)"] = grouped["Peratus (%)"].round(2)
        grouped.columns = ["Bekerja Dalam Bidang", "Bilangan Graduan", "Peratus (%)"]
        st.markdown("#### Jadual Bekerja Dalam Bidang")
        st.dataframe(grouped, height=200, hide_index=True, use_container_width=True)

def gaji_ikut_kumpulan():
    if "e_44_kumpulan" in filtered_df.columns:
        total = filtered_df[filtered_df["e_44_kumpulan"] != "Tidak Berkaitan"]["e_44_kumpulan"].count()

        kumpulan_gaji = filtered_df["e_44_kumpulan"]
        def group_gaji(value):
            if 0 < value <= 4:
                return "RM2,000 dan kebawah"
            elif 5 <= value <= 7:
                return "RM2,001 - RM3,000"
            elif value == 8:
                return "RM3,001 - RM4,000"
            elif value >= 11:
                return "RM4,001 dan keatas"
            else:
                return "meow"

        categories = ["RM2,000 dan kebawah", "RM2,001 - RM3,000", "RM3,001 - RM4,000", "RM4,001 dan keatas"]
        gaji_bins = kumpulan_gaji.apply(group_gaji)
        gaji_counts = gaji_bins.value_counts().reindex(categories, fill_value=0)
        gaji_df = pd.DataFrame({
            "Kategori Gaji": gaji_counts.index,
            "Bilangan Graduan": gaji_counts.values
        })
        gaji_df["angle"] = gaji_df["Bilangan Graduan"] / gaji_df["Bilangan Graduan"].sum() * 2 * np.pi
        gaji_df["color"] = gaji_df["Kategori Gaji"]
        st.markdown("##### Pendapatan Bulanan")
        fig = px.pie(
            gaji_df, 
            names="Kategori Gaji", 
            values="Bilangan Graduan", 
            category_orders={"Kategori Gaji": categories},
            hole=0,
        )
        fig.update_traces(
            textposition='inside',
            textinfo='percent',
            showlegend=True
        )
        fig.update_layout(
            width=350, height=330,
            legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center", yanchor="top"),
            margin=dict(t=2, b=2, l=2, r=2)
        )
        st.plotly_chart(fig, use_container_width=True)

def table_gaji_ikut_kumpulan():
    if not filtered_df.empty and "e_44_kumpulan" in filtered_df.columns:
        filtered = filtered_df[filtered_df["e_44_kumpulan"] != "Tidak Berkaitan"]
        
        def group_gaji(value):
            if 0 < value <= 4:
                return "RM2,000 dan kebawah"
            elif 5 <= value <= 7:
                return "RM2,001 - RM3,000"
            elif value == 8:
                return "RM3,001 - RM4,000"
            elif value >= 11:
                return "RM4,001 dan keatas"
            else:
                return "Lain-lain"
        
        categories = ["RM2,000 dan kebawah", "RM2,001 - RM3,000", "RM3,001 - RM4,000", "RM4,001 dan keatas"]
        gaji_bins = filtered["e_44_kumpulan"].apply(group_gaji)
        gaji_counts = gaji_bins.value_counts().reindex(categories, fill_value=0)
        
        gaji_table = pd.DataFrame({
            "Kategori Gaji": gaji_counts.index,
            "Bilangan Graduan": gaji_counts.values
        })
        
        total = gaji_table["Bilangan Graduan"].sum()
        gaji_table["Peratus (%)"] = gaji_table["Bilangan Graduan"] / total * 100
        gaji_table["Peratus (%)"] = gaji_table["Peratus (%)"].round(2)
        
        st.markdown("#### Jadual Pendapatan Bulanan")
        st.dataframe(gaji_table, height=200, hide_index=True, use_container_width=True)

def table_sektor_pekerjaan():
    if not filtered_df.empty and "e_45_label" in filtered_df.columns:
        filtered = filtered_df[
            (filtered_df["e_45_label"] != "Tidak Berkenaan") & 
            (filtered_df["e_statusPenyertaan"] == 1)
        ]
        grouped = (
            filtered.groupby("e_45_label")
            .size()
            .reset_index(name="Bilangan Graduan")
            .sort_values("Bilangan Graduan", ascending=False)
        )
        total = grouped["Bilangan Graduan"].sum()
        grouped["Peratus (%)"] = grouped["Bilangan Graduan"] / total * 100
        grouped["Peratus (%)"] = grouped["Peratus (%)"].round(2)
        grouped.columns = ["Sektor Pekerjaan", "Bilangan Graduan", "Peratus (%)"]
        st.markdown("#### Jadual Sektor Pekerjaan Graduan")
        st.dataframe(grouped, height=300, hide_index=True, use_container_width=True)

def table_sebab_tak_bekerja():
    if not filtered_df.empty and "e_54_label" in filtered_df.columns:
        df_status = filtered_df[filtered_df["e_status"] == 5]
        grouped = (
            df_status.groupby("e_54_label")
            .size()
            .reset_index(name="Bilangan Graduan")
            .sort_values("Bilangan Graduan", ascending=False)
        )
        total = grouped["Bilangan Graduan"].sum()
        grouped["Peratus (%)"] = grouped["Bilangan Graduan"] / total * 100
        grouped["Peratus (%)"] = grouped["Peratus (%)"].round(2)
        grouped.columns = ["Sebab Tidak Bekerja", "Bilangan Graduan", "Peratus (%)"]
        st.markdown("#### Jadual Sebab Tidak Bekerja")
        st.dataframe(grouped, height=300, hide_index=True, use_container_width=True)

def table_kumpulan_pekerjaan():
    if not filtered_df.empty and "e_41_a_label" in filtered_df.columns:
        filtered = filtered_df[
            (filtered_df["e_41_a_label"] != "Tidak Berkenaan") & 
            (filtered_df["e_statusPenyertaan"] == 1)
        ]
        grouped = (
            filtered.groupby("e_41_a_label")
            .size()
            .reset_index(name="Bilangan Graduan")
            .sort_values("Bilangan Graduan", ascending=False)
        )
        total = grouped["Bilangan Graduan"].sum()
        grouped["Peratus (%)"] = grouped["Bilangan Graduan"] / total * 100
        grouped["Peratus (%)"] = grouped["Peratus (%)"].round(2)
        grouped.columns = ["Kumpulan Pekerjaan", "Bilangan Graduan", "Peratus (%)"]
        st.markdown("#### Jadual Kumpulan Pekerjaan Graduan")
        st.dataframe(grouped, height=300, hide_index=True, use_container_width=True)

def table_taraf_pekerjaan():
    if not filtered_df.empty and "e_43_label" in filtered_df.columns:
        filtered = filtered_df[
            (filtered_df["e_43_label"] != "Tidak Berkenaan") & 
            (filtered_df["e_statusPenyertaan"] == 1)
        ]
        grouped = (
            filtered.groupby("e_43_label")
            .size()
            .reset_index(name="Bilangan Graduan")
            .sort_values("Bilangan Graduan", ascending=False)
        )
        total = grouped["Bilangan Graduan"].sum()
        grouped["Peratus (%)"] = grouped["Bilangan Graduan"] / total * 100
        grouped["Peratus (%)"] = grouped["Peratus (%)"].round(2)
        grouped.columns = ["Taraf Pekerjaan", "Bilangan Graduan", "Peratus (%)"]
        st.markdown("#### Jadual Taraf Pekerjaan Graduan")
        st.dataframe(grouped, height=300, hide_index=True, use_container_width=True)

def data_graduan():
    st.markdown("### Data Graduan")
    st.dataframe(filtered_df)

ringkasan_total_df = df_filtered_year[
    df_filtered_year["e_fakulti"].isin(selected_fakultis) & 
    df_filtered_year["e_program"].isin(selected_programs) &
    df_filtered_year["e_peringkat_label"].isin(selected_peringkat_pengajian)
] if selected_fakultis and selected_programs and selected_peringkat_pengajian else df_filtered_year

# --- DASHBOARD LAYOUT STARTS HERE ---

value_atas = st.columns((1,1,1,1,1))
layout = st.columns((0.65,1,1))
table = st.columns((1,1))

with value_atas[0]:
    jumlah_keseluruhan_graduan()
with value_atas[1]:
    peratusan_responden()
with value_atas[2]:
    graduate_marketability()
with value_atas[3]:
    graduate_employability()
with value_atas[4]:
    gaji_premium_kumpulan()

with layout[0]:
    gaji_ikut_kumpulan()
    plot_bekerja_dalam_bidang()
with layout[1]:
    histogram_sektor_pekerjaan()
    histogram_sebab_tak_bekerja()
with layout[2]:
    histogram_kumpulan_pekerjaan()
    histogram_taraf_pekerjaan()

with table[0]:
    table_sektor_pekerjaan()
    table_sebab_tak_bekerja()
    table_gaji_ikut_kumpulan()
with table[1]:
    table_kumpulan_pekerjaan()
    table_taraf_pekerjaan()
    table_bekerja_dalam_bidang()