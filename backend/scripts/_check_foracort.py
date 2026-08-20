import pandas as pd

df = pd.read_excel(r"D:\Nathan Wholesale Files\sUBLOCATION.xlsx")
df["ProductCode"] = df["ProductCode"].astype(str).str.strip()
codes = ["12616", "12617", "12618", "16308", "13320", "18076", "5861340", "5855227", "5854799"]
match = df[df["ProductCode"].isin(codes)]
print(match)
print("matches found:", len(match))
