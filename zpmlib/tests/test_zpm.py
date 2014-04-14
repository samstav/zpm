#  Copyright 2014 Rackspace, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import copy
import json
import mock
import os
import pytest
import shutil
import tarfile
import tempfile
import collections

from zpmlib import zpm

import yaml


class TestCreateProject:
    """
    Tests for :func:`zpmlib.zpm.create_project`.
    """

    def test_path_exists_not_dir(self):
        # A RuntimeError should be thrown if the target path exists and is
        # not a dir.
        _, tf = tempfile.mkstemp()
        with mock.patch('zpmlib.zpm._create_zar_yaml') as czy:
            with pytest.raises(RuntimeError):
                zpm.create_project(tf)
            assert czy.call_count == 0

    def test_path_does_not_exist(self):
        # If the path does not exist, `create_project` should create the
        # directory (including intermediate directories) and bootstrap an empty
        # project.
        tempdir = tempfile.mkdtemp()
        target_dir = os.path.join(tempdir, 'foo', 'bar')

        try:
            with mock.patch('zpmlib.zpm._create_zar_yaml') as czy:
                zpm.create_project(target_dir)
                assert czy.call_count == 1
        finally:
            shutil.rmtree(tempdir)

    def test_target_is_dir(self):
        # In this case, the target is a dir and it exists already.
        tempdir = tempfile.mkdtemp()
        try:
            with mock.patch('zpmlib.zpm._create_zar_yaml') as czy:
                zpm.create_project(tempdir)
                assert czy.call_count == 1
        finally:
            shutil.rmtree(tempdir)


class TestCreateZarYAML:
    """
    Tests for :func:`zpmlib.zpm._create_zar_yaml`.
    """

    def test_file_already_exists(self):
        tempdir = tempfile.mkdtemp()
        filepath = os.path.join(tempdir, 'zar.yaml')
        # "touch" the file
        open(filepath, 'w').close()
        try:
            with pytest.raises(RuntimeError):
                zpm._create_zar_yaml(tempdir)
        finally:
            shutil.rmtree(tempdir)

    def test_create_zar_yaml(self):
        # Test the creation of zar.yaml.
        tempdir = tempfile.mkdtemp()
        filepath = os.path.join(tempdir, 'zar.yaml')
        name = os.path.basename(tempdir)

        try:
            assert not os.path.exists(filepath)
            zaryaml = zpm._create_zar_yaml(tempdir)
            assert os.path.exists(filepath)
            with open(filepath) as fp:
                expected = yaml.load(zpm.render_zar_yaml(name))
                assert expected == yaml.load(fp)
            assert os.path.abspath(filepath) == os.path.abspath(zaryaml)
        finally:
            shutil.rmtree(tempdir)

    @mock.patch('yaml.constructor.SafeConstructor.construct_yaml_map')
    def test_key_ordering(self, yaml_map):
        # This makes yaml.safe_load use an OrderedDict instead of a
        # normal dict when loading a YAML mapping.
        ordered_dict = collections.OrderedDict()
        yaml_map.__iter__.return_value = iter(ordered_dict)

        # Test the creation of zar.yaml.
        tempdir = tempfile.mkdtemp()
        filepath = os.path.join(tempdir, 'zar.yaml')

        try:
            zpm._create_zar_yaml(tempdir)
            with open(filepath) as fp:
                loaded = yaml.safe_load(fp)
                tmpl = yaml.safe_load(zpm.render_zar_yaml(''))
                assert loaded.keys() == tmpl.keys()
        finally:
            shutil.rmtree(tempdir)


class TestFindUIUploads:
    """
    Tests for :func:`zpmlib.zpm._find_ui_uploads`.
    """

    def test_without_ui(self):
        matches = zpm._find_ui_uploads({}, None)
        assert matches == zpm._DEFAULT_UI_TEMPLATES

    def test_with_ui(self):
        zar = {'ui': ['x']}
        tar = mock.Mock(getnames=lambda: ['x', 'y'])
        matches = zpm._find_ui_uploads(zar, tar)
        assert sorted(matches) == ['x']

    def test_with_glob(self):
        zar = {'ui': ['x', 'ui/*']}
        tar = mock.Mock(getnames=lambda: ['x', 'y', 'ui/x', 'ui/y'])
        matches = zpm._find_ui_uploads(zar, tar)
        assert sorted(matches) == ['ui/x', 'ui/y', 'x']


def test__prepare_job():
    # Test for `zpmlib.zpm._prepare_job`.

    # Contents of `myapp.json`, which is expected to be in the `myapp.zar`
    # archive.
    myapp_json = [
        {'exec': {'args': 'myapp.py', 'path': 'file://python2.7:python'},
         'file_list': [{'device': 'python2.7'}, {'device': 'stdout'}],
         'name': 'myapp'}
    ]
    zar = {'meta': {'name': 'myapp'}}
    zar_swift_url = ('swift://AUTH_469a9cd20b5a4fc5be9438f66bb5ee04/'
                     'test_container/hello.zar')

    # Expected result
    exp_job_json = copy.deepcopy(myapp_json)
    exp_job_json[0]['file_list'].append(
        {'device': 'image', 'path': zar_swift_url}
    )

    tempdir = tempfile.mkdtemp()
    try:
        tempzar = os.path.join(tempdir, 'myapp.zar')
        with tarfile.open(tempzar, 'w:gz') as tf:
            temp_myapp_json = os.path.join(tempdir, 'myapp.json')
            with open(temp_myapp_json, 'w') as fp:
                json.dump(myapp_json, fp)
            tf.add(temp_myapp_json, arcname='myapp.json')

        with tarfile.open(tempzar, 'r:gz') as tf:
            job = zpm._prepare_job(tf, zar, zar_swift_url)
        assert exp_job_json == job
    finally:
        shutil.rmtree(tempdir)
