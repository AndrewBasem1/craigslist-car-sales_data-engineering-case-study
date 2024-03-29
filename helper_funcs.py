import zipfile
import csv
import io
from pathlib import Path
from typing import Iterator
from sqlalchemy import Engine
from models import CraigslistVehicleRecordRead
from models import CraigslistVehicleRecord
from os import environ
from sqlmodel import Session
from db_engine import db_engine
from pydantic import ValidationError as PydanticValidationError
from re import match


def strip_strings_and_replace_empty_strings_with_none(input_str: str) -> str:
    input_str = input_str.strip()
    return input_str if input_str != "" else None


def extract_cylinders_int_value_from_cylinders_str(cylinders_str: str) -> int:
    if cylinders_str is None:
        return None
    pat = r"(\d+)"
    match_obj = match(pat, cylinders_str)
    if match_obj:
        return int(match_obj.group(1))
    else:
        return None


def create_csv_records_iterator_from_zip_file(
    zip_file_path: Path = environ.get("ZIP_FILE_NAME"),
    csv_file_name: str = environ.get("CSV_FILE_NAME"),
) -> Iterator[dict[str, str]]:
    """
    helper function for reading csv lines from a zip file without extracting it to save memory (disk and RAM)

    ## Parameters
    - zip_file_path: `pathlib.Path` object of the zip file
    - csv_file_name: `str` name of the csv file inside the zip file

    ## Returns
    - `Iterator[dict[str, str]]` object that yields a dict of csv record values with the csv headers as keys

    ## Usage
    calling `next()` on the Iterator object returned will return the next csv record as a dict
    """
    with zipfile.ZipFile(zip_file_path) as zip_file:
        with zip_file.open(csv_file_name) as csv_file:
            decoded_csv_file = io.TextIOWrapper(csv_file, encoding="utf-8")
            csv_reader = csv.reader(decoded_csv_file)
            csv_headers = next(csv_reader)
            for line in csv_reader:
                line = map(strip_strings_and_replace_empty_strings_with_none, line)
                line_record_dict = dict(zip(csv_headers, line))
                line_record_dict[
                    "cylinders"
                ] = extract_cylinders_int_value_from_cylinders_str(
                    line_record_dict["cylinders"]
                )
                yield line_record_dict


def validate_craigslist_vehicle_record_dict(
    craigslist_vehicle_record_dict: dict[str, str]
) -> CraigslistVehicleRecord:
    """
    validates a Craigslist vehicle record dict and returns a CraigslistVehicleRecord object.
    """
    craigslist_vehicle_record_without_id = CraigslistVehicleRecordRead.model_validate(
        craigslist_vehicle_record_dict
    )
    craigslist_vehicle_record = CraigslistVehicleRecord.model_validate(
        craigslist_vehicle_record_without_id
    )
    return craigslist_vehicle_record


def insert_batch_of_craigslist_vehicle_records(
    batch_of_craigslist_vehicle_records: list[CraigslistVehicleRecord],
    db_engine: Engine = db_engine,
) -> None:
    """
    inserts a batch of Craigslist vehicle records into the database.
    """
    with Session(db_engine) as session:
        session.add_all(batch_of_craigslist_vehicle_records)
        session.commit()


def migrate_craigslist_records_csv_from_zip_to_db(
    zip_file_path: Path = environ.get("ZIP_FILE_NAME"),
    csv_file_name: str = environ.get("CSV_FILE_NAME"),
    batch_size: int = 10_000,
    max_rows_to_parse: int = None,
) -> None:
    """
    parses and inserts the Craigslist vehicle records from a zip file into the database.
    """
    csv_lines_iterator = create_csv_records_iterator_from_zip_file(
        zip_file_path=zip_file_path, csv_file_name=csv_file_name
    )
    # getting the first line for the col headers
    rows_count_in_current_batch = 0
    total_rows_parsed = 0
    total_rows_inserted = 0
    current_batch = []
    while True:
        try:
            print(f"total_rows_parsed: {total_rows_parsed}", end="\r")
            if rows_count_in_current_batch < batch_size:
                current_record_dict = next(csv_lines_iterator)
                try:
                    craiglist_vehicle_record = validate_craigslist_vehicle_record_dict(
                        current_record_dict
                    )
                    current_batch.append(craiglist_vehicle_record)
                    rows_count_in_current_batch += 1
                    total_rows_parsed += 1
                except PydanticValidationError as e:
                    print(e)
                    print(current_record_dict)
                    print("-" * 30)
                    continue
            else:
                print(f"starting batch insertion of {batch_size} records")
                insert_batch_of_craigslist_vehicle_records(current_batch)
                total_rows_inserted += rows_count_in_current_batch
                print(
                    f"finished batch insertion of {batch_size} records, total_rows_inserted: {total_rows_inserted}"
                )
                if max_rows_to_parse and total_rows_parsed >= max_rows_to_parse:
                    break
                rows_count_in_current_batch = 0
                current_batch = []
        except StopIteration:
            break
    if current_batch:
        print(f"starting batch insertion of {batch_size} records")
        insert_batch_of_craigslist_vehicle_records(current_batch)
        total_rows_inserted += rows_count_in_current_batch
        print(
            f"finished batch insertion of {batch_size} records, total_rows_inserted: {total_rows_inserted}"
        )
    print(f"total_rows_parsed: {total_rows_parsed}")
    print(f"total_rows_inserted: {total_rows_inserted}")
    return None


if __name__ == "__main__":
    migrate_craigslist_records_csv_from_zip_to_db()
