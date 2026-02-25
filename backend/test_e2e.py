"""
End-to-end tests for SortWise backend.
Uses real files on disk — no mocks.
Run from repo root: source venv/bin/activate && python -m pytest backend/test_e2e.py -v
"""
import csv
import io
import os
import struct
import tempfile
import unittest

import piexif
from PIL import Image

# Import backend directly
from backend import main


# ---------------------------------------------------------------------------
# File factory helpers
# ---------------------------------------------------------------------------

def make_jpeg(path, width=100, height=100, exif_date=None, gps=None):
    """Create a real JPEG file, optionally with EXIF date/GPS."""
    img = Image.new('RGB', (width, height), color=(128, 64, 32))
    exif_dict = {"0th": {}, "Exif": {}, "GPS": {}}

    if exif_date:
        # DateTimeOriginal tag
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date.encode()

    if gps:
        lat, lon = gps

        def to_dms(val):
            val = abs(val)
            d = int(val)
            m = int((val - d) * 60)
            s = round(((val - d) * 60 - m) * 60 * 100)
            return ((d, 1), (m, 1), (s, 100))

        exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b'N' if lat >= 0 else b'S'
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = to_dms(lat)
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b'E' if lon >= 0 else b'W'
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = to_dms(lon)

    exif_bytes = piexif.dump(exif_dict)
    img.save(path, "JPEG", exif=exif_bytes)


def make_png(path, width=200, height=100):
    """Create a real PNG (landscape by default)."""
    img = Image.new('RGB', (width, height), color=(0, 128, 255))
    img.save(path, "PNG")


def make_gif(path):
    """Create a minimal valid GIF."""
    img = Image.new('P', (10, 10))
    img.save(path, "GIF")


def make_dummy(path):
    """Create a tiny dummy binary file (used for .mov/.mp4/.avi)."""
    with open(path, 'wb') as f:
        f.write(b'\x00' * 16)


def base_options(**overrides):
    opts = {
        'folders': [],
        'sortOptions': {},
        'fileOperation': 'move',
        'conflictResolution': 'rename',
        'dateSortOption': 'yearMonth',
    }
    opts.update(overrides)
    return opts


def read_log(log_path):
    rows = []
    with open(log_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestE2EFileTypeSorting(unittest.TestCase):

    def test_jpg_moves_to_photos(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'photo.jpg'))
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            result = main.sort_files(opts)
            self.assertEqual(result['status'], 'success')
            self.assertTrue(os.path.exists(os.path.join(d, 'Photos', 'photo.jpg')))
            self.assertFalse(os.path.exists(os.path.join(d, 'photo.jpg')))

    def test_png_moves_to_photos(self):
        with tempfile.TemporaryDirectory() as d:
            make_png(os.path.join(d, 'img.png'))
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, 'Photos', 'img.png')))

    def test_gif_moves_to_gifs_not_photos(self):
        with tempfile.TemporaryDirectory() as d:
            make_gif(os.path.join(d, 'anim.gif'))
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, 'GIFs', 'anim.gif')))
            self.assertFalse(os.path.exists(os.path.join(d, 'Photos')))

    def test_mp4_moves_to_videos(self):
        with tempfile.TemporaryDirectory() as d:
            make_dummy(os.path.join(d, 'clip.mp4'))
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, 'Videos', 'clip.mp4')))

    def test_avi_moves_to_videos(self):
        with tempfile.TemporaryDirectory() as d:
            make_dummy(os.path.join(d, 'clip.avi'))
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, 'Videos', 'clip.avi')))

    def test_mov_moves_to_videos(self):
        with tempfile.TemporaryDirectory() as d:
            make_dummy(os.path.join(d, 'clip.mov'))
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, 'Videos', 'clip.mov')))

    def test_screenshot_moves_to_screenshots(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'Screenshot 2024-01-01.jpg'))
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            main.sort_files(opts)
            self.assertTrue(os.path.exists(
                os.path.join(d, 'Screenshots', 'Screenshot 2024-01-01.jpg')))

    def test_unsupported_file_stays_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            doc = os.path.join(d, 'notes.txt')
            open(doc, 'w').close()
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            main.sort_files(opts)
            self.assertTrue(os.path.exists(doc))


class TestE2EDateSorting(unittest.TestCase):

    def test_exif_date_year_month(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'img.jpg'), exif_date='2023:06:15 10:30:00')
            opts = base_options(folders=[d], sortOptions={'exifDate': True}, dateSortOption='yearMonth')
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, '2023', '06', 'img.jpg')))

    def test_exif_date_year_only(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'img.jpg'), exif_date='2021:11:05 08:00:00')
            opts = base_options(folders=[d], sortOptions={'exifDate': True}, dateSortOption='year')
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, '2021', 'img.jpg')))

    def test_no_exif_falls_back_to_filesystem_date(self):
        with tempfile.TemporaryDirectory() as d:
            # Plain JPEG with no EXIF date — fallback uses mtime
            img_path = os.path.join(d, 'noexif.jpg')
            img = Image.new('RGB', (10, 10))
            img.save(img_path, "JPEG")

            import time
            mtime = os.path.getmtime(img_path)
            expected_year = str(int(time.strftime('%Y', time.localtime(mtime))))

            opts = base_options(folders=[d], sortOptions={'exifDate': True}, dateSortOption='year')
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, expected_year, 'noexif.jpg')))


class TestE2EOrientationSorting(unittest.TestCase):

    def test_landscape_jpeg(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'wide.jpg'), width=1920, height=1080)
            opts = base_options(folders=[d], sortOptions={'orientation': True})
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, 'Landscape', 'wide.jpg')))

    def test_portrait_jpeg(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'tall.jpg'), width=1080, height=1920)
            opts = base_options(folders=[d], sortOptions={'orientation': True})
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, 'Portrait', 'tall.jpg')))


class TestE2ECopyMode(unittest.TestCase):

    def test_copy_leaves_original_in_place(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'photo.jpg'))
            opts = base_options(folders=[d], sortOptions={'fileType': True}, fileOperation='copy')
            main.sort_files(opts)
            self.assertTrue(os.path.exists(os.path.join(d, 'photo.jpg')))
            self.assertTrue(os.path.exists(os.path.join(d, 'Photos', 'photo.jpg')))


class TestE2EConflictResolution(unittest.TestCase):

    def test_rename_on_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            # Sort once to get photo.jpg into Photos/ (copy mode so original stays)
            make_jpeg(os.path.join(d, 'photo.jpg'))
            opts_copy = base_options(folders=[d], sortOptions={'fileType': True}, fileOperation='copy')
            main.sort_files(opts_copy)

            photos_dir = os.path.join(d, 'Photos')
            self.assertTrue(os.path.exists(os.path.join(photos_dir, 'photo.jpg')))
            # Now sort again in move mode — conflict should trigger rename
            opts_move = base_options(folders=[d], sortOptions={'fileType': True},
                                     fileOperation='move', conflictResolution='rename')
            main.sort_files(opts_move)

            # The second copy got renamed to photo_1.jpg
            self.assertTrue(os.path.exists(os.path.join(photos_dir, 'photo_1.jpg')))

    def test_overwrite_on_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            # Original content
            src = os.path.join(d, 'photo.jpg')
            make_jpeg(src)
            with open(src, 'rb') as f:
                original_bytes = f.read()

            photos_dir = os.path.join(d, 'Photos')
            os.makedirs(photos_dir)
            # Pre-place a different file
            make_png(os.path.join(photos_dir, 'photo.jpg'))

            opts = base_options(folders=[d], sortOptions={'fileType': True},
                                conflictResolution='overwrite')
            main.sort_files(opts)

            dest = os.path.join(photos_dir, 'photo.jpg')
            self.assertTrue(os.path.exists(dest))
            with open(dest, 'rb') as f:
                self.assertEqual(f.read(), original_bytes)


class TestE2EDeduplication(unittest.TestCase):

    def test_duplicate_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            # Two files with identical content
            make_jpeg(os.path.join(d, 'img1.jpg'))
            import shutil
            shutil.copy2(os.path.join(d, 'img1.jpg'), os.path.join(d, 'img2.jpg'))

            opts = base_options(folders=[d], sortOptions={'fileType': True, 'deduplication': True})
            result = main.sort_files(opts)
            self.assertEqual(result['status'], 'success')

            log = read_log(result['logFile'])
            statuses = [r['Status'] for r in log]
            self.assertIn('Moved', statuses)
            self.assertIn('Skipped (Duplicate)', statuses)

    def test_unique_files_all_moved(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'a.jpg'), width=100, height=100)
            make_jpeg(os.path.join(d, 'b.jpg'), width=200, height=150)

            opts = base_options(folders=[d], sortOptions={'fileType': True, 'deduplication': True})
            result = main.sort_files(opts)

            log = read_log(result['logFile'])
            moved = [r for r in log if r['Status'] == 'Moved']
            self.assertEqual(len(moved), 2)


class TestE2ELivePhotos(unittest.TestCase):

    def test_jpg_mov_pair_sorted_to_live_photos(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'burst.jpg'))
            make_dummy(os.path.join(d, 'burst.mov'))

            opts = base_options(folders=[d], sortOptions={'livePhotos': True})
            main.sort_files(opts)

            live_dir = os.path.join(d, 'Live_Photos')
            self.assertTrue(os.path.exists(os.path.join(live_dir, 'burst.jpg')))
            self.assertTrue(os.path.exists(os.path.join(live_dir, 'burst.mov')))

    def test_live_photos_copy_mode(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'burst.jpg'))
            make_dummy(os.path.join(d, 'burst.mov'))

            opts = base_options(folders=[d], sortOptions={'livePhotos': True}, fileOperation='copy')
            main.sort_files(opts)

            live_dir = os.path.join(d, 'Live_Photos')
            # Originals stay in place
            self.assertTrue(os.path.exists(os.path.join(d, 'burst.jpg')))
            self.assertTrue(os.path.exists(os.path.join(d, 'burst.mov')))
            # Copies in Live_Photos
            self.assertTrue(os.path.exists(os.path.join(live_dir, 'burst.jpg')))
            self.assertTrue(os.path.exists(os.path.join(live_dir, 'burst.mov')))


class TestE2EUndoSort(unittest.TestCase):

    def test_undo_restores_moved_file(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'photo.jpg'))
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            result = main.sort_files(opts)

            dest = os.path.join(d, 'Photos', 'photo.jpg')
            self.assertTrue(os.path.exists(dest))

            undo_result = main.undo_sort(result['logFile'])
            self.assertEqual(undo_result['status'], 'success')
            self.assertTrue(os.path.exists(os.path.join(d, 'photo.jpg')))
            self.assertFalse(os.path.exists(dest))

    def test_undo_works_after_rename_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'photo.jpg'))
            photos_dir = os.path.join(d, 'Photos')
            os.makedirs(photos_dir)
            make_jpeg(os.path.join(photos_dir, 'photo.jpg'))

            opts = base_options(folders=[d], sortOptions={'fileType': True},
                                conflictResolution='rename')
            result = main.sort_files(opts)

            renamed = os.path.join(photos_dir, 'photo_1.jpg')
            self.assertTrue(os.path.exists(renamed))

            undo_result = main.undo_sort(result['logFile'])
            self.assertEqual(undo_result['status'], 'success')
            self.assertFalse(os.path.exists(renamed))
            # Original filename restored at source path
            self.assertTrue(os.path.exists(os.path.join(d, 'photo.jpg')))

    def test_undo_cleans_empty_subdirs(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'photo.jpg'), exif_date='2023:06:15 10:00:00')
            opts = base_options(folders=[d], sortOptions={'fileType': True, 'exifDate': True},
                                dateSortOption='yearMonth')
            result = main.sort_files(opts)

            dest_dir = os.path.join(d, 'Photos', '2023', '06')
            self.assertTrue(os.path.exists(os.path.join(dest_dir, 'photo.jpg')))

            main.undo_sort(result['logFile'])
            self.assertFalse(os.path.exists(dest_dir))


class TestE2ECombinedSorting(unittest.TestCase):

    def test_file_type_and_date_combined(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'photo.jpg'), exif_date='2022:03:20 09:00:00')
            opts = base_options(
                folders=[d],
                sortOptions={'fileType': True, 'exifDate': True},
                dateSortOption='yearMonth',
            )
            main.sort_files(opts)
            self.assertTrue(os.path.exists(
                os.path.join(d, 'Photos', '2022', '03', 'photo.jpg')))

    def test_file_type_and_orientation_combined(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'wide.jpg'), width=1920, height=1080)
            opts = base_options(
                folders=[d],
                sortOptions={'fileType': True, 'orientation': True},
            )
            main.sort_files(opts)
            self.assertTrue(os.path.exists(
                os.path.join(d, 'Photos', 'Landscape', 'wide.jpg')))


class TestE2ELogFile(unittest.TestCase):

    def test_log_contains_expected_columns(self):
        with tempfile.TemporaryDirectory() as d:
            make_jpeg(os.path.join(d, 'photo.jpg'))
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            result = main.sort_files(opts)

            rows = read_log(result['logFile'])
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertIn('Original Filename', row)
            self.assertIn('Source Path', row)
            self.assertIn('Destination Folder', row)
            self.assertIn('Status', row)
            self.assertIn('Destination Filename', row)
            self.assertEqual(row['Status'], 'Moved')
            self.assertEqual(row['Original Filename'], 'photo.jpg')
            self.assertEqual(row['Destination Filename'], 'photo.jpg')

    def test_unsupported_file_logged_as_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, 'doc.pdf'), 'w').close()
            opts = base_options(folders=[d], sortOptions={'fileType': True})
            result = main.sort_files(opts)

            rows = read_log(result['logFile'])
            self.assertEqual(len(rows), 1)
            self.assertIn('Skipped', rows[0]['Status'])


if __name__ == '__main__':
    unittest.main()
