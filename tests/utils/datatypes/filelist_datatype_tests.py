import uuid
from unittest.mock import Mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.datastructures import MultiValueDict
from arches.app.datatypes.datatypes import DataTypeFactory
from django.test import TestCase
from arches.app.models.models import File as FileModel

# these tests can be run from the command line via
# python manage.py test tests.utils.datatypes.filelist_datatype_tests --settings="tests.test_settings"


class FileListDataTypeTests(TestCase):
    def test_tile_transform(self):
        value1 = "testfile1.png,testfile2.png"

        value2 = [
            {
                "name": "testfile3.png",
                "altText": "Test File 3",
                "attribution": "archesproject",
                "description": "A File for Testing",
                "title": "Test File 3",
            },
            {
                "name": "testfile4.png",
                "altText": {"en": {"value": "Test File 4", "direction": "ltr"}},
                "attribution": {"en": {"value": "archesproject", "direction": "ltr"}},
                "description": {
                    "en": {"value": "A File for Testing", "direction": "ltr"}
                },
                "title": {"en": {"value": "Test File 4", "direction": "ltr"}},
            },
        ]

        datatype = DataTypeFactory().get_instance("file-list")

        with self.subTest("comma-separated string input"):
            tile_value = datatype.transform_value_for_tile(value1)
            self.assertEqual(tile_value[0]["name"], "testfile1.png")
            self.assertEqual(tile_value[1]["name"], "testfile2.png")

        with self.subTest("list with one dict"):
            # A single file dict must be wrapped in a list; the parent
            # handles list-of-dicts.  Localized metadata (altText etc.)
            # is populated by the arches_querysets subclass, not here.
            tile_value = datatype.transform_value_for_tile([value2[0]])
            self.assertEqual(tile_value[0]["name"], "testfile3.png")

        with self.subTest("A list of dictionaries input"):
            # The parent populates basic tile fields; localized metadata
            # (altText, attribution, description, title) is handled by
            # the arches_querysets subclass.
            tile_value = datatype.transform_value_for_tile(value2)
            self.assertEqual(tile_value[0]["name"], "testfile3.png")
            self.assertEqual(tile_value[1]["name"], "testfile4.png")

    def test_transform_value_for_tile_preserves_existing_file_id(self):
        """Files that already have a valid UUID file_id should pass through
        unchanged without creating a new File record in the database."""
        datatype = DataTypeFactory().get_instance("file-list")
        existing_file_id = str(uuid.uuid4())
        existing_url = f"/files/{existing_file_id}"

        value = [
            {
                "file_id": existing_file_id,
                "url": existing_url,
                "name": "existing_photo.jpg",
                "type": "image/jpeg",
                "status": "uploaded",
                "size": 12345,
            }
        ]

        file_count_before = FileModel.objects.count()
        tile_value = datatype.transform_value_for_tile(value)
        file_count_after = FileModel.objects.count()

        with self.subTest("file_id is preserved unchanged"):
            self.assertEqual(tile_value[0]["file_id"], existing_file_id)

        with self.subTest("url is preserved unchanged"):
            self.assertEqual(tile_value[0]["url"], existing_url)

        with self.subTest("name is preserved"):
            self.assertEqual(tile_value[0]["name"], "existing_photo.jpg")

        with self.subTest("no new File record is created in the database"):
            self.assertEqual(file_count_before, file_count_after)

    def test_transform_value_for_tile_strips_frontend_fields_from_existing_file(self):
        """Frontend-only fields (file blob reference, node_id) must be stripped
        from already-stored files so they are not persisted in tile data."""
        datatype = DataTypeFactory().get_instance("file-list")
        existing_file_id = str(uuid.uuid4())

        value = [
            {
                "file_id": existing_file_id,
                "url": f"/files/{existing_file_id}",
                "name": "existing_photo.jpg",
                "type": "image/jpeg",
                "status": "uploaded",
                "file": {"objectURL": "blob:http://localhost/abc123"},
                "node_id": "0a883b80-2fb6-11ed-be5f-5254008afee6",
            }
        ]

        tile_value = datatype.transform_value_for_tile(value)

        with self.subTest("file blob reference is stripped"):
            self.assertNotIn("file", tile_value[0])

        with self.subTest("node_id is stripped"):
            self.assertNotIn("node_id", tile_value[0])

        with self.subTest("legitimate fields are kept"):
            self.assertEqual(tile_value[0]["file_id"], existing_file_id)
            self.assertEqual(tile_value[0]["name"], "existing_photo.jpg")

    def test_transform_value_for_tile_upload_key_is_not_treated_as_existing(self):
        """A file_id that is an upload key (e.g. 'file-list_{tileid}-{nodeid}')
        rather than a UUID must not trigger the already-stored early-return.
        The file must be processed normally, creating a new File record."""
        datatype = DataTypeFactory().get_instance("file-list")
        upload_key = "file-list_abc-tile-123"

        value = [
            {
                "file_id": upload_key,
                "url": None,
                "name": "new_photo.jpg",
                "type": "image/jpeg",
                "node_id": "0a883b80-2fb6-11ed-be5f-5254008afee6",
                "file": {"objectURL": "blob:http://localhost/xyz"},
            }
        ]

        file_count_before = FileModel.objects.count()
        tile_value = datatype.transform_value_for_tile(value)
        file_count_after = FileModel.objects.count()

        with self.subTest("a new UUID file_id is generated (not the upload key)"):
            self.assertNotEqual(tile_value[0]["file_id"], upload_key)
            # The generated file_id should be a valid UUID
            uuid.UUID(tile_value[0]["file_id"])

        with self.subTest("a new File record is created"):
            self.assertEqual(file_count_after - file_count_before, 1)

    def test_transform_value_for_tile_mixed_existing_and_new_files(self):
        """A list mixing already-stored files (have UUID file_id) and new files
        (no file_id) should preserve existing file_ids and only create a
        new File record for the genuinely new file."""
        datatype = DataTypeFactory().get_instance("file-list")
        existing_file_id = str(uuid.uuid4())
        existing_url = f"/files/{existing_file_id}"

        value = [
            {
                "file_id": existing_file_id,
                "url": existing_url,
                "name": "existing_photo.jpg",
                "type": "image/jpeg",
                "status": "uploaded",
            },
            {
                "name": "new_photo.jpg",
                "type": "image/jpeg",
            },
        ]

        file_count_before = FileModel.objects.count()
        tile_value = datatype.transform_value_for_tile(value)
        file_count_after = FileModel.objects.count()

        with self.subTest("existing file_id is preserved"):
            self.assertEqual(tile_value[0]["file_id"], existing_file_id)

        with self.subTest("existing url is preserved"):
            self.assertEqual(tile_value[0]["url"], existing_url)

        with self.subTest("new file receives a generated file_id"):
            self.assertIsNotNone(tile_value[1].get("file_id"))
            self.assertNotEqual(tile_value[1]["file_id"], existing_file_id)

        with self.subTest("exactly one new File record is created (for the new file)"):
            self.assertEqual(file_count_after - file_count_before, 1)

        with self.subTest("no File record is created for the existing file_id"):
            self.assertFalse(FileModel.objects.filter(fileid=existing_file_id).exists())

    def test_get_files_from_request(self):
        datatype = DataTypeFactory().get_instance("file-list")
        nodeid = str(uuid.uuid4())
        tile_id = str(uuid.uuid4())

        file1 = SimpleUploadedFile("file1.png", b"content1", content_type="image/png")
        file2 = SimpleUploadedFile("file2.png", b"content2", content_type="image/png")
        preloaded = SimpleUploadedFile(
            "preloaded.png", b"preloaded", content_type="image/png"
        )

        node_key = f"file-list_{nodeid}"
        tile_key = f"file-list_{tile_id}-{nodeid}"

        mock_tile = Mock()
        mock_tile.tileid = tile_id
        request = Mock()

        with self.subTest("files found via nodeid key"):
            request.FILES = MultiValueDict({node_key: [file1, file2]})
            result = datatype._get_files_from_request(request, nodeid)
            self.assertEqual(result, [file1, file2])

        with self.subTest("preloaded and regular files are concatenated"):
            request.FILES = MultiValueDict(
                {f"{node_key}_preloaded": [preloaded], node_key: [file1]}
            )
            result = datatype._get_files_from_request(request, nodeid)
            self.assertEqual(result, [preloaded, file1])

        with self.subTest("falls back to tile-scoped key when nodeid key is empty"):
            request.FILES = MultiValueDict({tile_key: [file1, file2]})
            result = datatype._get_files_from_request(request, nodeid, tile=mock_tile)
            self.assertEqual(result, [file1, file2])

        with self.subTest("tile-scoped preloaded and regular files are concatenated"):
            request.FILES = MultiValueDict(
                {f"{tile_key}_preloaded": [preloaded], tile_key: [file1]}
            )
            result = datatype._get_files_from_request(request, nodeid, tile=mock_tile)
            self.assertEqual(result, [preloaded, file1])

        with self.subTest("nodeid key takes priority over tile-scoped key"):
            request.FILES = MultiValueDict({node_key: [file1], tile_key: [file2]})
            result = datatype._get_files_from_request(request, nodeid, tile=mock_tile)
            self.assertEqual(result, [file1])

        with self.subTest("no files, no tile → empty list"):
            request.FILES = MultiValueDict({})
            result = datatype._get_files_from_request(request, nodeid)
            self.assertEqual(result, [])

        with self.subTest("no files anywhere, tile provided → empty list"):
            request.FILES = MultiValueDict({})
            result = datatype._get_files_from_request(request, nodeid, tile=mock_tile)
            self.assertEqual(result, [])
