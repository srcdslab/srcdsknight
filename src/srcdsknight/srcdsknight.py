from __future__ import annotations

import logging
import os
import shutil
import tarfile
from typing import Any, Dict

import click
import requests
import yaml

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
    if os.path.exists(f"{cachePath}/{filename}") and cache:
        logger.info(f"Skipping existing cache for {fileextension} {downloadURL}")
    else:
        logger.info(f"Downloading <{downloadURL}> into <{cachePath}/{filename}>")
        try:
            r = requests.get(downloadURL, allow_redirects=True)
            open(f"{cachePath}/{filename}", 'wb').write(r.content)
        except Exception as exc:
            if skipFailedDownload:
                logger.warn(f"Skipping invalid download file <{downloadURL}>")
                return False
            raise exc
    return True


def extract_dependency(
    *,
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
        logger.info(f"Extracting {linkName}")
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


def install_dependencies(*, config: Dict[str, Any]) -> None:
    folders = config['folders']
    directories = folders['directories']
    installPath = os.path.abspath(config['installPath'])
    rootPath = f"{installPath}/.srcdsknight"
    cachePath = f"{rootPath}/cache"
    packagePath = f"{rootPath}/package"

    if not os.path.exists(installPath):
        os.makedirs(installPath)

    if not os.path.exists(cachePath):
        os.makedirs(cachePath)

    if not os.path.exists(packagePath):
        os.makedirs(packagePath)

    os.chdir(installPath)

    if os.path.exists(packagePath):
        shutil.rmtree(packagePath)

    for linkName, linkConfig in config["links"].items():
        downloadURL = linkConfig['url']
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


@click.command()
@click.option('--config-file', default="config.yml", help='Configuration file path.')
@click.option('-v', '--verbose', count=True, help="Verbosity level")
def cli(config_file: str, verbose: int) -> None:

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

    install_dependencies(config=config)
