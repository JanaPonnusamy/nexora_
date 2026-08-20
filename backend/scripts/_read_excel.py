import pandas as pd

path = r"D:\Nathan Wholesale Files\sUBLOCATION.xlsx"
df = pd.read_excel(path)
print(df.columns.tolist())
print(df.head(20))
print("shape:", df.shape)
