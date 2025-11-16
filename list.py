import pandas as pd

df = pd.read_excel("pages\\Data SKPG\\Data SKPG 2024.xlsx")

columns_list = df.columns.tolist()

df_columns = pd.DataFrame({
  "No.": range(1, len(columns_list) + 1),
  "Kod yang ada": columns_list
})

df_columns.to_excel("list_kod_medan.xlsx", index=False)