import csv
import datetime
import hashlib
import os
import sys
import json
import shutil
import exifread
from PIL import Image
from geopy.geocoders import Nominatim

# Bug 5 fix: module-level geolocator with timeout (avoid recreating per call)
geolocator = Nominatim(user_agent="sortwise/1.0", timeout=5)


def get_exif_data(file_path):
    with open(file_path, 'rb') as f:
        tags = exifread.process_file(f, details=False)
    return tags


def get_location(tags):
    lat_ref = tags.get('GPS GPSLatitudeRef')
    lat = tags.get('GPS GPSLatitude')
    lon_ref = tags.get('GPS GPSLongitudeRef')
    lon = tags.get('GPS GPSLongitude')

    if not all([lat, lat_ref, lon, lon_ref]):
        return None

    def to_decimal(dms, ref):
        degrees = dms.values[0].num / dms.values[0].den
        minutes = dms.values[1].num / dms.values[1].den
        seconds = dms.values[2].num / dms.values[2].den
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref.values in ['S', 'W']:
            decimal *= -1
        return decimal

    latitude = to_decimal(lat, lat_ref)
    longitude = to_decimal(lon, lon_ref)

    # Bug 5 fix: wrapped in try-except so geocoding failures don't crash the sort
    try:
        location = geolocator.reverse((latitude, longitude), exactly_one=True)
        if location:
            return location.raw['address']
    except Exception:
        pass

    return None


def get_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()


def sort_files(options):
    folders = options.get('folders', [])
    sort_options = options.get('sortOptions', {})
    file_operation = options.get('fileOperation', 'move')
    conflict_resolution = options.get('conflictResolution', 'rename')
    # Bug 1 fix: read dateSortOption from options (was undefined variable)
    date_sort_option = options.get('dateSortOption', 'yearMonth')
    hashes = set()
    log_file = os.path.join(os.path.expanduser("~"), "sortwise_log.csv")
    supported_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.mov', '.mp4', '.avi']

    with open(log_file, 'w', newline='') as f:
        writer = csv.writer(f)
        # Bug 3 fix: added 'Destination Filename' column to track actual name after rename
        writer.writerow(['Original Filename', 'Source Path', 'Destination Folder', 'Status', 'Destination Filename'])

        all_files = []
        for folder in folders:
            for root, _, files in os.walk(folder):
                for file in files:
                    all_files.append((folder, os.path.join(root, file)))
        total_files = len(all_files)
        processed_files = 0

        for folder, file_path in all_files:
            filename = os.path.basename(file_path)
            processed_files += 1
            progress = int((processed_files / total_files) * 100)
            print(json.dumps({"type": "progress", "value": progress}))
            sys.stdout.flush()

            _, ext = os.path.splitext(filename)
            if ext.lower() not in supported_extensions:
                writer.writerow([filename, file_path, '', f'Skipped (Unsupported File Type: {ext})', ''])
                continue

            try:
                if sort_options.get('deduplication'):
                    file_hash = get_file_hash(file_path)
                    if file_hash in hashes:
                        writer.writerow([filename, file_path, '', 'Skipped (Duplicate)', ''])
                        continue
                    hashes.add(file_hash)

                target_subfolder = ''

                if sort_options.get('fileType'):
                    file_type = ext.lstrip('.').lower()
                    if 'screenshot' in filename.lower():
                        target_subfolder = os.path.join(target_subfolder, 'Screenshots')
                    # Bug 2 fix: GIF checked before Photos so it isn't swallowed by the Photos branch
                    elif file_type == 'gif':
                        target_subfolder = os.path.join(target_subfolder, 'GIFs')
                    elif file_type in ['jpg', 'jpeg', 'png']:
                        target_subfolder = os.path.join(target_subfolder, 'Photos')
                    elif file_type in ['mov', 'mp4', 'avi']:
                        target_subfolder = os.path.join(target_subfolder, 'Videos')

                tags = get_exif_data(file_path)

                if sort_options.get('exifDate'):
                    date_str = None
                    if 'EXIF DateTimeOriginal' in tags:
                        date_str = str(tags['EXIF DateTimeOriginal'])

                    if date_str and len(date_str) >= 7:
                        year = date_str[0:4]
                        month = date_str[5:7]
                        if year.isdigit() and month.isdigit():
                            # Bug 1 fix: date_sort_option now correctly comes from options
                            if date_sort_option == 'yearMonth':
                                target_subfolder = os.path.join(target_subfolder, year, month)
                            else:
                                target_subfolder = os.path.join(target_subfolder, year)
                    else:
                        # Fallback to file system date
                        file_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                        year = str(file_date.year)
                        month = str(file_date.month).zfill(2)
                        if date_sort_option == 'yearMonth':
                            target_subfolder = os.path.join(target_subfolder, year, month)
                        else:
                            target_subfolder = os.path.join(target_subfolder, year)

                if sort_options.get('cameraModel') and 'Image Model' in tags:
                    model = str(tags['Image Model']).replace(' ', '_')
                    target_subfolder = os.path.join(target_subfolder, model)

                if sort_options.get('location'):
                    address = get_location(tags)
                    if address:
                        country = address.get('country', 'Unknown_Country')
                        # Fallback chain: city → town → village → Unknown_City
                        city = address.get('city') or address.get('town') or address.get('village', 'Unknown_City')
                        target_subfolder = os.path.join(target_subfolder, country, city)

                if sort_options.get('orientation'):
                    # Bug 6 fix: targeted try-except so a bad file only skips orientation,
                    # not the entire file sort
                    try:
                        with Image.open(file_path) as img:
                            width, height = img.size
                            orientation = 'Landscape' if width > height else 'Portrait'
                            target_subfolder = os.path.join(target_subfolder, orientation)
                    except Exception:
                        pass

                if sort_options.get('livePhotos'):
                    base, ext_lp = os.path.splitext(filename)
                    if ext_lp.lower() == '.jpg':
                        mov_file = os.path.join(os.path.dirname(file_path), base + '.mov')
                        if os.path.exists(mov_file):
                            live_photo_folder_abs = os.path.join(folder, target_subfolder, 'Live_Photos')
                            if not os.path.exists(live_photo_folder_abs):
                                os.makedirs(live_photo_folder_abs)

                            jpg_dest = os.path.join(live_photo_folder_abs, filename)
                            mov_dest = os.path.join(live_photo_folder_abs, base + '.mov')

                            # Bug 4 fix: respect file_operation (was always shutil.move)
                            if file_operation == 'copy':
                                shutil.copy2(file_path, jpg_dest)
                                shutil.copy2(mov_file, mov_dest)
                                op_status = 'Copied'
                            else:
                                shutil.move(file_path, jpg_dest)
                                shutil.move(mov_file, mov_dest)
                                op_status = 'Moved'

                            # Bug 4 fix: log absolute path so undo can find the files
                            writer.writerow([filename, file_path, live_photo_folder_abs, op_status, filename])
                            writer.writerow([base + '.mov', mov_file, live_photo_folder_abs, op_status, base + '.mov'])
                            continue

                if target_subfolder:
                    destination_folder = os.path.join(folder, target_subfolder)
                    if not os.path.exists(destination_folder):
                        os.makedirs(destination_folder)

                    destination_path = os.path.join(destination_folder, filename)
                    dest_filename = filename  # tracks actual name after any rename

                    if os.path.exists(destination_path) and conflict_resolution == 'rename':
                        base, ext_cr = os.path.splitext(filename)
                        i = 1
                        while os.path.exists(os.path.join(destination_folder, f'{base}_{i}{ext_cr}')):
                            i += 1
                        dest_filename = f'{base}_{i}{ext_cr}'
                        destination_path = os.path.join(destination_folder, dest_filename)

                    if file_operation == 'copy':
                        shutil.copy2(file_path, destination_path)
                        # Bug 3 fix: log dest_filename (actual name) not original filename
                        writer.writerow([filename, file_path, destination_folder, 'Copied', dest_filename])
                    else:
                        shutil.move(file_path, destination_path)
                        writer.writerow([filename, file_path, destination_folder, 'Moved', dest_filename])

            except Exception as e:
                writer.writerow([filename, file_path, '', f'Error: {e}', ''])
                continue

    return {"status": "success", "message": "Files sorted successfully.", "logFile": log_file}


def undo_sort(log_file):
    if not os.path.exists(log_file):
        return {"status": "error", "message": "Log file not found."}

    destination_folders = set()
    with open(log_file, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header

        for row in reader:
            if len(row) < 4:
                continue
            original_filename, source_path, destination_folder, status = row[:4]
            # Bug 3 fix: use actual destination filename (col 5) if present, else original name
            dest_filename = row[4] if len(row) > 4 and row[4] else original_filename

            if status in ['Moved', 'Copied']:
                destination_path = os.path.join(destination_folder, dest_filename)
                if os.path.exists(destination_path):
                    shutil.move(destination_path, source_path)
                destination_folders.add(destination_folder)

    for folder in sorted(list(destination_folders), reverse=True):
        if os.path.exists(folder) and not os.listdir(folder):
            os.rmdir(folder)

    return {"status": "success", "message": "Undo operation completed successfully."}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'undo':
            try:
                log_file_path = sys.argv[2]
                result = undo_sort(log_file_path)
                print(json.dumps(result))
            except Exception as e:
                print(json.dumps({"status": "error", "message": str(e)}))
        else:
            try:
                options = json.loads(sys.argv[1])
                result = sort_files(options)
                print(json.dumps(result))
            except json.JSONDecodeError:
                print(json.dumps({"status": "error", "message": "Invalid JSON input."}))
            except Exception as e:
                print(json.dumps({"status": "error", "message": str(e)}))
    else:
        print(json.dumps({"status": "error", "message": "No options provided."}))
