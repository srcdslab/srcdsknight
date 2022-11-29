from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tarfile
import time
from typing import Any, Dict

import click
import git
import requests
import yaml
from git.remote import FetchInfo
from git.repo.base import Repo

logger = logging.getLogger(__name__)


def download_dependency(
    *,
    filename: str,
    fileextension: str,
    cache: bool,
    cachePath: str,
    downloadURL: str,
    skipFailedDownload: bool,
) -> bool:

    is_valid = False
    if os.path.exists(f"{cachePath}/{filename}"):
        if "tar.gz" in fileextension:
            try:
                my_tar = tarfile.open(f"{cachePath}/{filename}")
                my_tar.close()
                is_valid = True
            except tarfile.ReadError:
                pass
        elif "git" in fileextension:
            repo = git.Repo(f"{cachePath}/{filename}")
            fetchinfo = repo.remotes.origin.pull()
            logger.info(
                f"Pull result flag of <{cachePath}/{filename}>: {fetchinfo[0].flags}"
            )
            if fetchinfo[0].flags == FetchInfo.HEAD_UPTODATE:
                return False
            is_valid = True

    if is_valid and cache:
        logger.info(f"Skipping existing cache for {fileextension} {downloadURL}")
    else:
        logger.info(f"Downloading <{downloadURL}> into <{cachePath}/{filename}>")
        try:
            if "tar.gz" in fileextension:
                r = requests.get(downloadURL, allow_redirects=True)
                open(f"{cachePath}/{filename}", 'wb').write(r.content)
            elif "git" in fileextension:
                Repo.clone_from(downloadURL, f"{cachePath}/{filename}")
        except Exception as exc:
            if skipFailedDownload:
                logger.warn(f"Skipping invalid download file <{downloadURL}>")
                return False
            raise exc
    return True


def extract_dependency(
    *,
    fileextension: str,
    linkName: str,
    filename: str,
    cache: bool,
    cachePath: str,
    packagePath: str,
    skipFailedExtract: bool,
) -> bool:
    if os.path.exists(f"{packagePath}/{linkName}") and cache:
        logger.info(f"Skipping existing cache for folder {linkName}")
    else:
        logger.info(
            f"Extracting <{cachePath}/{filename}> into <{packagePath}/{linkName}>"
        )
        if "tar.gz" in fileextension:
            try:
                my_tar = tarfile.open(f"{cachePath}/{filename}")
            except tarfile.ReadError as exc:
                if skipFailedExtract:
                    logger.warn(f"Skipping invalid tar file <cache/{filename}>")
                    return False
                raise exc
            my_tar.extractall(
                f"{packagePath}/{linkName}"
            )  # specify which folder to extract to
            my_tar.close()
        elif "git" in fileextension:
            shutil.copytree(
                f"{cachePath}/{filename}",
                f"{packagePath}/{linkName}",
                dirs_exist_ok=True,
            )
    return True


def copy_folder_content(
    *, extractPath: str, subPath: str, installPath: str, directories: Dict[str, Any]
) -> None:
    source_dir = f"{extractPath}"
    if subPath:
        source_dir = f"{source_dir}/{subPath}"
    logger.debug(f"Copying content of <{source_dir}> into <{installPath}>")
    for directoryName, directoryConfig in directories.items():
        file_name = directoryConfig["path"]
        source_subdir = f"{source_dir}/{file_name}"
        desination_subdir = f"{installPath}/{directoryName}"
        if os.path.exists(source_subdir):
            logger.info(f"Copying <{source_subdir}> into <{desination_subdir}>")
            if os.path.exists(source_subdir):
                shutil.copytree(source_subdir, desination_subdir, dirs_exist_ok=True)


def install_dependency(
    *,
    extractPath: str,
    installPath: str,
    folders: Dict[str, Any],
    directories: Dict[str, Any],
) -> None:
    for folderName, folderConfig in folders.items():
        if folderName == "gametype":
            copy_folder_content(
                extractPath=extractPath,
                subPath=folderConfig["path"],
                installPath=installPath,
                directories=directories,
            )
        elif folderName == "common":
            for path in folderConfig["paths"]:
                copy_folder_content(
                    extractPath=extractPath,
                    subPath=path,
                    installPath=installPath,
                    directories=directories,
                )


def install_dependencies(*, config: Dict[str, Any], sync: bool) -> None:
    mycwd = os.getcwd()
    folders = config['folders']
    directories = folders['directories']
    installPath = os.path.abspath(config['installPath'])
    rootPath = f"{installPath}/.srcdsknight"
    cachePath = f"{rootPath}/cache"
    packagePath = f"{rootPath}/package"

    logger.info(f"Installing dependencies in <{installPath}>")

    if (
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", installPath]
        ).returncode
        != 0
    ):
        logger.warn("Could not set target repository as a safe git path")

    if not os.path.exists(installPath):
        os.makedirs(installPath)

    if not os.path.exists(cachePath):
        os.makedirs(cachePath)

    if os.path.exists(packagePath):
        shutil.rmtree(packagePath)

    if not os.path.exists(packagePath):
        os.makedirs(packagePath)

    os.chdir(installPath)

    for linkName, linkConfig in config["links"].items():
        syncLink = linkConfig.get('sync', False)
        if sync and not syncLink:
            continue

        downloadURL = linkConfig['url']

        if syncLink:
            fileextension = "git"
        else:
            fileextension = "tar.gz"
        filename = f'{linkName}.{fileextension}'
        cache = config["cache"]["enabled"]
        skipFailedDownload = config["skipFailedDownload"]
        skipFailedExtract = config["skipFailedDownload"]

        if download_dependency(
            filename=filename,
            fileextension=fileextension,
            cache=cache,
            cachePath=cachePath,
            downloadURL=downloadURL,
            skipFailedDownload=skipFailedDownload,
        ) and extract_dependency(
            fileextension=fileextension,
            linkName=linkName,
            filename=filename,
            cache=cache,
            cachePath=cachePath,
            packagePath=packagePath,
            skipFailedExtract=skipFailedExtract,
        ):
            install_dependency(
                extractPath=f"{packagePath}/{linkName}",
                installPath=installPath,
                folders=folders,
                directories=directories,
            )
            shutil.rmtree(f"{packagePath}/{linkName}")

    if os.path.exists(packagePath):
        shutil.rmtree(packagePath)

    os.chdir(mycwd)


def sync_dependencies(*, config: Dict[str, Any], sync_seconds: int) -> None:
    while True:
        install_dependencies(config=config, sync=True)
        wait_seconds: int = sync_seconds
        logger.info(f"Next sync in {wait_seconds} seconds")
        time.sleep(wait_seconds)


@click.command()
@click.option('--config-file', default="config.yml", help='Configuration file path.')
@click.option('-s', '--sync', is_flag=True, help="Start in sync mode")
@click.option(
    '-ss', '--sync-seconds', type=click.INT, help="Sync every X seconds", default=60
)
@click.option('-v', '--verbose', count=True, help="Verbosity level")
def cli(config_file: str, sync: bool, sync_seconds: int, verbose: int) -> None:

    log_level = logging.ERROR
    if verbose > 2:
        log_level = logging.DEBUG
    elif verbose > 1:
        log_level = logging.INFO
    elif verbose > 0:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        format='%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z',
    )

    with open(config_file, "r") as file:
        config = yaml.safe_load(file)

    logger.debug(f"Config file <{config_file}> loaded")

    if not sync:
        install_dependencies(config=config, sync=sync)
    else:
        sync_dependencies(config=config, sync_seconds=sync_seconds)
