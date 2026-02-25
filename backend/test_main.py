import csv
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock, mock_open

from backend import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_options(**overrides):
    """Return a minimal valid options dict, overridable per test."""
    opts = {
        'folders': ['/photos'],
        'sortOptions': {},
        'fileOperation': 'move',
        'conflictResolution': 'rename',
        'dateSortOption': 'yearMonth',
    }
    opts.update(overrides)
    return opts


def _run_sort(options, walk_return, exif_return=None, exists_return=False):
    """
    Convenience wrapper: patches the common collaborators and runs sort_files.
    Returns (result, mock_move, mock_copy, mock_makedirs).
    """
    exif_return = exif_return or {}
    with patch('backend.main.os.walk') as mock_walk, \
         patch('backend.main.os.path.exists') as mock_exists, \
         patch('backend.main.os.makedirs') as mock_makedirs, \
         patch('backend.main.shutil.move') as mock_move, \
         patch('backend.main.shutil.copy2') as mock_copy, \
         patch('backend.main.get_exif_data') as mock_exif, \
         patch('builtins.open', mock_open()):

        mock_walk.return_value = walk_return
        mock_exists.return_value = exists_return
        mock_exif.return_value = exif_return

        result = main.sort_files(options)

    return result, mock_move, mock_copy, mock_makedirs


# ---------------------------------------------------------------------------
# File Type sorting
# ---------------------------------------------------------------------------

class TestFileTypeSorting(unittest.TestCase):

    def test_jpg_goes_to_photos(self):
        opts = _base_options(sortOptions={'fileType': True})
        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])])
        makedirs.assert_any_call('/photos/Photos')
        move.assert_called_once_with('/photos/img.jpg', '/photos/Photos/img.jpg')

    def test_png_goes_to_photos(self):
        opts = _base_options(sortOptions={'fileType': True})
        _, move, _, _ = _run_sort(opts, [('/photos', [], ['img.png'])])
        move.assert_called_once_with('/photos/img.png', '/photos/Photos/img.png')

    def test_mp4_goes_to_videos(self):
        opts = _base_options(sortOptions={'fileType': True})
        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['clip.mp4'])])
        makedirs.assert_any_call('/photos/Videos')
        move.assert_called_once_with('/photos/clip.mp4', '/photos/Videos/clip.mp4')

    def test_avi_goes_to_videos(self):
        opts = _base_options(sortOptions={'fileType': True})
        _, move, _, _ = _run_sort(opts, [('/photos', [], ['clip.avi'])])
        move.assert_called_once_with('/photos/clip.avi', '/photos/Videos/clip.avi')

    # Bug 2 regression: GIFs must NOT go to Photos
    def test_gif_goes_to_gifs_not_photos(self):
        opts = _base_options(sortOptions={'fileType': True})
        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['anim.gif'])])
        makedirs.assert_any_call('/photos/GIFs')
        move.assert_called_once_with('/photos/anim.gif', '/photos/GIFs/anim.gif')
        # Verify Photos was never created
        paths_created = [call.args[0] for call in makedirs.call_args_list]
        self.assertNotIn('/photos/Photos', paths_created)

    def test_screenshot_goes_to_screenshots(self):
        opts = _base_options(sortOptions={'fileType': True})
        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['Screenshot 2024.jpg'])])
        makedirs.assert_any_call('/photos/Screenshots')
        move.assert_called_once_with('/photos/Screenshot 2024.jpg', '/photos/Screenshots/Screenshot 2024.jpg')

    def test_unsupported_extension_is_skipped(self):
        opts = _base_options(sortOptions={'fileType': True})
        _, move, copy, _ = _run_sort(opts, [('/photos', [], ['doc.pdf'])])
        move.assert_not_called()
        copy.assert_not_called()

    def test_mixed_files_sorted_correctly(self):
        opts = _base_options(sortOptions={'fileType': True})
        _, move, _, makedirs = _run_sort(
            opts, [('/photos', [], ['photo.jpg', 'video.mp4', 'anim.gif'])]
        )
        self.assertEqual(move.call_count, 3)
        makedirs_paths = {c.args[0] for c in makedirs.call_args_list}
        self.assertIn('/photos/Photos', makedirs_paths)
        self.assertIn('/photos/Videos', makedirs_paths)
        self.assertIn('/photos/GIFs', makedirs_paths)


# ---------------------------------------------------------------------------
# Date sorting
# ---------------------------------------------------------------------------

class TestDateSorting(unittest.TestCase):

    def _exif_with_date(self, date_str='2023:06:15 10:30:00'):
        mock_tag = MagicMock()
        mock_tag.__str__ = lambda s: date_str
        return {'EXIF DateTimeOriginal': mock_tag}

    # Bug 1 regression: yearMonth must work without NameError
    def test_exif_date_year_month(self):
        opts = _base_options(sortOptions={'exifDate': True}, dateSortOption='yearMonth')
        exif = self._exif_with_date('2023:06:15 10:30:00')
        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])], exif_return=exif)
        makedirs.assert_any_call('/photos/2023/06')
        move.assert_called_once_with('/photos/img.jpg', '/photos/2023/06/img.jpg')

    def test_exif_date_year_only(self):
        opts = _base_options(sortOptions={'exifDate': True}, dateSortOption='year')
        exif = self._exif_with_date('2023:06:15 10:30:00')
        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])], exif_return=exif)
        makedirs.assert_any_call('/photos/2023')
        move.assert_called_once_with('/photos/img.jpg', '/photos/2023/img.jpg')

    @patch('backend.main.os.path.getmtime')
    @patch('backend.main.datetime.datetime')
    def test_fallback_to_filesystem_date_year_month(self, mock_dt, mock_mtime):
        mock_dt.fromtimestamp.return_value = MagicMock(year=2022, month=3)
        opts = _base_options(sortOptions={'exifDate': True}, dateSortOption='yearMonth')
        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])], exif_return={})
        makedirs.assert_any_call('/photos/2022/03')
        move.assert_called_once_with('/photos/img.jpg', '/photos/2022/03/img.jpg')

    @patch('backend.main.os.path.getmtime')
    @patch('backend.main.datetime.datetime')
    def test_fallback_to_filesystem_date_year_only(self, mock_dt, mock_mtime):
        mock_dt.fromtimestamp.return_value = MagicMock(year=2022, month=3)
        opts = _base_options(sortOptions={'exifDate': True}, dateSortOption='year')
        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])], exif_return={})
        makedirs.assert_any_call('/photos/2022')
        move.assert_called_once_with('/photos/img.jpg', '/photos/2022/img.jpg')


# ---------------------------------------------------------------------------
# Camera model sorting
# ---------------------------------------------------------------------------

class TestCameraModelSorting(unittest.TestCase):

    def test_camera_model_creates_subfolder(self):
        mock_model = MagicMock()
        mock_model.__str__ = lambda s: 'iPhone 14 Pro'
        exif = {'Image Model': mock_model}
        opts = _base_options(sortOptions={'cameraModel': True})
        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])], exif_return=exif)
        makedirs.assert_any_call('/photos/iPhone_14_Pro')
        move.assert_called_once_with('/photos/img.jpg', '/photos/iPhone_14_Pro/img.jpg')

    def test_no_camera_model_tag_skips(self):
        opts = _base_options(sortOptions={'cameraModel': True})
        _, move, _, _ = _run_sort(opts, [('/photos', [], ['img.jpg'])], exif_return={})
        move.assert_not_called()


# ---------------------------------------------------------------------------
# Orientation sorting
# ---------------------------------------------------------------------------

class TestOrientationSorting(unittest.TestCase):

    def test_landscape_image(self):
        opts = _base_options(sortOptions={'orientation': True})
        mock_img = MagicMock()
        mock_img.size = (1920, 1080)
        mock_img.__enter__ = lambda s: mock_img
        mock_img.__exit__ = MagicMock(return_value=False)
        with patch('backend.main.Image.open', return_value=mock_img):
            _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])])
        makedirs.assert_any_call('/photos/Landscape')
        move.assert_called_once_with('/photos/img.jpg', '/photos/Landscape/img.jpg')

    def test_portrait_image(self):
        opts = _base_options(sortOptions={'orientation': True})
        mock_img = MagicMock()
        mock_img.size = (1080, 1920)
        mock_img.__enter__ = lambda s: mock_img
        mock_img.__exit__ = MagicMock(return_value=False)
        with patch('backend.main.Image.open', return_value=mock_img):
            _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])])
        makedirs.assert_any_call('/photos/Portrait')
        move.assert_called_once_with('/photos/img.jpg', '/photos/Portrait/img.jpg')

    # Bug 6 regression: corrupted image must not crash sort of the whole file
    def test_corrupted_image_skips_orientation_only(self):
        opts = _base_options(sortOptions={'fileType': True, 'orientation': True})
        with patch('backend.main.Image.open', side_effect=Exception("corrupt")):
            _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])])
        # File still sorted into Photos (fileType), orientation just skipped
        makedirs.assert_any_call('/photos/Photos')
        move.assert_called_once_with('/photos/img.jpg', '/photos/Photos/img.jpg')


# ---------------------------------------------------------------------------
# Location sorting
# ---------------------------------------------------------------------------

class TestLocationSorting(unittest.TestCase):

    def _make_gps_tags(self):
        def _ratio(val):
            r = MagicMock()
            r.num = val
            r.den = 1
            return r

        lat_tag = MagicMock()
        lat_tag.values = [_ratio(37), _ratio(46), _ratio(29)]
        lat_ref = MagicMock()
        lat_ref.values = 'N'
        lon_tag = MagicMock()
        lon_tag.values = [_ratio(122), _ratio(25), _ratio(9)]
        lon_ref = MagicMock()
        lon_ref.values = 'W'

        return {
            'GPS GPSLatitude': lat_tag,
            'GPS GPSLatitudeRef': lat_ref,
            'GPS GPSLongitude': lon_tag,
            'GPS GPSLongitudeRef': lon_ref,
        }

    def test_location_creates_country_city_subfolders(self):
        opts = _base_options(sortOptions={'location': True})
        fake_address = {'country': 'United States', 'city': 'San Francisco'}
        with patch('backend.main.geolocator.reverse') as mock_reverse:
            mock_loc = MagicMock()
            mock_loc.raw = {'address': fake_address}
            mock_reverse.return_value = mock_loc
            _, move, _, makedirs = _run_sort(
                opts, [('/photos', [], ['img.jpg'])], exif_return=self._make_gps_tags()
            )
        makedirs.assert_any_call('/photos/United States/San Francisco')
        move.assert_called_once_with('/photos/img.jpg', '/photos/United States/San Francisco/img.jpg')

    def test_location_geocoding_failure_skips_gracefully(self):
        opts = _base_options(sortOptions={'location': True})
        with patch('backend.main.geolocator.reverse', side_effect=Exception("timeout")):
            _, move, _, _ = _run_sort(
                opts, [('/photos', [], ['img.jpg'])], exif_return=self._make_gps_tags()
            )
        # File with no valid location is not moved (no target_subfolder)
        move.assert_not_called()

    def test_missing_gps_tags_skips_location(self):
        opts = _base_options(sortOptions={'location': True})
        _, move, _, _ = _run_sort(opts, [('/photos', [], ['img.jpg'])], exif_return={})
        move.assert_not_called()


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication(unittest.TestCase):

    def test_duplicate_file_is_skipped(self):
        opts = _base_options(sortOptions={'deduplication': True, 'fileType': True})
        with patch('backend.main.os.walk') as mock_walk, \
             patch('backend.main.os.path.exists', return_value=False), \
             patch('backend.main.os.makedirs'), \
             patch('backend.main.shutil.move') as mock_move, \
             patch('backend.main.shutil.copy2'), \
             patch('backend.main.get_exif_data', return_value={}), \
             patch('backend.main.get_file_hash', side_effect=['abc123', 'abc123']), \
             patch('builtins.open', mock_open()):

            mock_walk.return_value = [('/photos', [], ['img1.jpg', 'img2.jpg'])]
            main.sort_files(opts)

        # Only the first file should be moved
        self.assertEqual(mock_move.call_count, 1)
        mock_move.assert_called_once_with('/photos/img1.jpg', '/photos/Photos/img1.jpg')

    def test_unique_files_are_not_skipped(self):
        opts = _base_options(sortOptions={'deduplication': True, 'fileType': True})
        with patch('backend.main.os.walk') as mock_walk, \
             patch('backend.main.os.path.exists', return_value=False), \
             patch('backend.main.os.makedirs'), \
             patch('backend.main.shutil.move') as mock_move, \
             patch('backend.main.shutil.copy2'), \
             patch('backend.main.get_exif_data', return_value={}), \
             patch('backend.main.get_file_hash', side_effect=['hash_a', 'hash_b']), \
             patch('builtins.open', mock_open()):

            mock_walk.return_value = [('/photos', [], ['img1.jpg', 'img2.jpg'])]
            main.sort_files(opts)

        self.assertEqual(mock_move.call_count, 2)


# ---------------------------------------------------------------------------
# File operation: Copy vs Move
# ---------------------------------------------------------------------------

class TestFileOperation(unittest.TestCase):

    def test_copy_operation_uses_copy2(self):
        opts = _base_options(sortOptions={'fileType': True}, fileOperation='copy')
        _, move, copy, _ = _run_sort(opts, [('/photos', [], ['img.jpg'])])
        copy.assert_called_once_with('/photos/img.jpg', '/photos/Photos/img.jpg')
        move.assert_not_called()

    def test_move_operation_uses_move(self):
        opts = _base_options(sortOptions={'fileType': True}, fileOperation='move')
        _, move, copy, _ = _run_sort(opts, [('/photos', [], ['img.jpg'])])
        move.assert_called_once_with('/photos/img.jpg', '/photos/Photos/img.jpg')
        copy.assert_not_called()


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------

class TestConflictResolution(unittest.TestCase):

    def test_rename_on_conflict(self):
        opts = _base_options(sortOptions={'fileType': True}, conflictResolution='rename')
        with patch('backend.main.os.walk') as mock_walk, \
             patch('backend.main.os.path.exists') as mock_exists, \
             patch('backend.main.os.makedirs'), \
             patch('backend.main.shutil.move') as mock_move, \
             patch('backend.main.shutil.copy2'), \
             patch('backend.main.get_exif_data', return_value={}), \
             patch('builtins.open', mock_open()):

            mock_walk.return_value = [('/photos', [], ['img.jpg'])]
            # First exists() for destination_folder → False (folder doesn't exist)
            # Second exists() for destination_path → True (file already there → trigger rename)
            # Third exists() for renamed path → False (no further conflict)
            mock_exists.side_effect = [False, True, False]
            main.sort_files(opts)

        mock_move.assert_called_once_with('/photos/img.jpg', '/photos/Photos/img_1.jpg')

    def test_overwrite_on_conflict(self):
        opts = _base_options(sortOptions={'fileType': True}, conflictResolution='overwrite')
        with patch('backend.main.os.walk') as mock_walk, \
             patch('backend.main.os.path.exists') as mock_exists, \
             patch('backend.main.os.makedirs'), \
             patch('backend.main.shutil.move') as mock_move, \
             patch('backend.main.shutil.copy2'), \
             patch('backend.main.get_exif_data', return_value={}), \
             patch('builtins.open', mock_open()):

            mock_walk.return_value = [('/photos', [], ['img.jpg'])]
            mock_exists.side_effect = [False, True]
            main.sort_files(opts)

        # With overwrite, file is moved to the original path without rename
        mock_move.assert_called_once_with('/photos/img.jpg', '/photos/Photos/img.jpg')


# ---------------------------------------------------------------------------
# Live Photos
# ---------------------------------------------------------------------------

class TestLivePhotos(unittest.TestCase):

    def test_live_photo_pair_moved_together(self):
        opts = _base_options(sortOptions={'livePhotos': True}, fileOperation='move')
        with patch('backend.main.os.walk') as mock_walk, \
             patch('backend.main.os.path.exists') as mock_exists, \
             patch('backend.main.os.makedirs') as mock_makedirs, \
             patch('backend.main.shutil.move') as mock_move, \
             patch('backend.main.shutil.copy2'), \
             patch('backend.main.get_exif_data', return_value={}), \
             patch('builtins.open', mock_open()):

            mock_walk.return_value = [('/photos', [], ['burst.jpg', 'burst.mov'])]
            # exists() calls: destination_folder check (False), then .mov companion check (True)
            mock_exists.side_effect = lambda p: p.endswith('.mov')
            main.sort_files(opts)

        # Both jpg and mov moved to Live_Photos
        self.assertEqual(mock_move.call_count, 2)
        dest_folder = '/photos/Live_Photos'
        mock_move.assert_any_call('/photos/burst.jpg', f'{dest_folder}/burst.jpg')
        mock_move.assert_any_call('/photos/burst.mov', f'{dest_folder}/burst.mov')

    # Bug 4 regression: copy operation must use copy2, not move
    def test_live_photo_pair_copied_together(self):
        opts = _base_options(sortOptions={'livePhotos': True}, fileOperation='copy')
        with patch('backend.main.os.walk') as mock_walk, \
             patch('backend.main.os.path.exists') as mock_exists, \
             patch('backend.main.os.makedirs'), \
             patch('backend.main.shutil.move') as mock_move, \
             patch('backend.main.shutil.copy2') as mock_copy, \
             patch('backend.main.get_exif_data', return_value={}), \
             patch('builtins.open', mock_open()):

            mock_walk.return_value = [('/photos', [], ['burst.jpg', 'burst.mov'])]
            mock_exists.side_effect = lambda p: p.endswith('.mov')
            main.sort_files(opts)

        self.assertEqual(mock_copy.call_count, 2)
        mock_move.assert_not_called()


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

class TestUndoSort(unittest.TestCase):

    def _write_log(self, path, rows):
        with open(path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Original Filename', 'Source Path', 'Destination Folder', 'Status', 'Destination Filename'])
            writer.writerows(rows)

    def test_undo_moves_file_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, 'src', 'img.jpg')
            dest_dir = os.path.join(tmpdir, 'Photos')
            dest_file = os.path.join(dest_dir, 'img.jpg')

            os.makedirs(os.path.dirname(src))
            os.makedirs(dest_dir)
            open(dest_file, 'w').close()  # create the "moved" file

            log = os.path.join(tmpdir, 'test_log.csv')
            self._write_log(log, [
                ['img.jpg', src, dest_dir, 'Moved', 'img.jpg']
            ])

            result = main.undo_sort(log)

            self.assertEqual(result['status'], 'success')
            self.assertTrue(os.path.exists(src))

    # Bug 3 regression: undo must work when file was renamed by conflict resolution
    def test_undo_handles_renamed_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, 'src', 'img.jpg')
            dest_dir = os.path.join(tmpdir, 'Photos')
            dest_file = os.path.join(dest_dir, 'img_1.jpg')  # renamed!

            os.makedirs(os.path.dirname(src))
            os.makedirs(dest_dir)
            open(dest_file, 'w').close()

            log = os.path.join(tmpdir, 'test_log.csv')
            self._write_log(log, [
                ['img.jpg', src, dest_dir, 'Moved', 'img_1.jpg']
            ])

            result = main.undo_sort(log)

            self.assertEqual(result['status'], 'success')
            self.assertTrue(os.path.exists(src))

    def test_undo_missing_log_returns_error(self):
        result = main.undo_sort('/nonexistent/path/log.csv')
        self.assertEqual(result['status'], 'error')

    def test_undo_removes_empty_destination_folder(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, 'src', 'img.jpg')
            dest_dir = os.path.join(tmpdir, 'Photos')
            dest_file = os.path.join(dest_dir, 'img.jpg')

            os.makedirs(os.path.dirname(src))
            os.makedirs(dest_dir)
            open(dest_file, 'w').close()

            log = os.path.join(tmpdir, 'test_log.csv')
            self._write_log(log, [
                ['img.jpg', src, dest_dir, 'Moved', 'img.jpg']
            ])

            main.undo_sort(log)

        # Empty Photos dir should be cleaned up
        self.assertFalse(os.path.exists(dest_dir))

    def test_undo_skips_already_missing_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, 'img.jpg')
            dest_dir = os.path.join(tmpdir, 'Photos')
            log = os.path.join(tmpdir, 'test_log.csv')
            self._write_log(log, [
                ['img.jpg', src, dest_dir, 'Moved', 'img.jpg']
            ])
            # No file in dest_dir — undo should not crash
            result = main.undo_sort(log)

        self.assertEqual(result['status'], 'success')

    def test_undo_ignores_skipped_and_error_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = os.path.join(tmpdir, 'img.jpg')
            dest_dir = os.path.join(tmpdir, 'Photos')
            log = os.path.join(tmpdir, 'test_log.csv')
            self._write_log(log, [
                ['img.jpg', src, dest_dir, 'Skipped (Duplicate)', ''],
                ['bad.txt', src, dest_dir, 'Error: some error', ''],
            ])
            result = main.undo_sort(log)

        self.assertEqual(result['status'], 'success')


# ---------------------------------------------------------------------------
# Combined / integration-style
# ---------------------------------------------------------------------------

class TestCombinedSorting(unittest.TestCase):

    def test_file_type_and_date_combined(self):
        opts = _base_options(
            sortOptions={'fileType': True, 'exifDate': True},
            dateSortOption='yearMonth',
        )
        mock_tag = MagicMock()
        mock_tag.__str__ = lambda s: '2023:06:15 10:30:00'
        exif = {'EXIF DateTimeOriginal': mock_tag}

        _, move, _, makedirs = _run_sort(opts, [('/photos', [], ['img.jpg'])], exif_return=exif)

        makedirs.assert_any_call('/photos/Photos/2023/06')
        move.assert_called_once_with('/photos/img.jpg', '/photos/Photos/2023/06/img.jpg')


if __name__ == '__main__':
    unittest.main()
