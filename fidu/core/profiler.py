import pandas as pd


def profile_dataframe(df: pd.DataFrame) -> dict:
    profile = {"row_count": len(df), "columns": []}
    for column in df.columns:
        s = df[column]
        non_null = s.dropna()
        col = {"name": column, "dtype": str(s.dtype), "null_count": int(s.isna().sum()), "null_rate": round(float(s.isna().mean()), 4), "distinct_count": int(s.nunique(dropna=True)), "distinct_rate": round(float(s.nunique(dropna=True) / len(df)), 4) if len(df) else 0}
        if pd.api.types.is_numeric_dtype(s):
            col.update({"inferred_type": "numeric", "min": float(non_null.min()) if len(non_null) else None, "max": float(non_null.max()) if len(non_null) else None})
        elif pd.api.types.is_datetime64_any_dtype(s):
            col.update({"inferred_type": "date", "min": str(non_null.min()) if len(non_null) else None, "max": str(non_null.max()) if len(non_null) else None})
        else:
            parsed = pd.to_datetime(s, errors="coerce")
            if parsed.notna().mean() > 0.8:
                col.update({"inferred_type": "date", "min": str(parsed.min()), "max": str(parsed.max())})
            else:
                col.update({"inferred_type": "string", "top_values": s.dropna().astype(str).value_counts().head(20).to_dict()})
        profile["columns"].append(col)
    return profile
