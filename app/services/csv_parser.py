import csv
import io

CSV_COLUMNS = [
    "id",
    "name",
    "gender",
    "gender_probability",
    "age",
    "age_group",
    "country_id",
    "country_name",
    "country_probability",
    "created_at",
]


def generate_csv(profiles):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(CSV_COLUMNS)  # Header
    for profile in profiles:
        writer.writerow([getattr(profile, col) for col in CSV_COLUMNS])
    return output.getvalue()
