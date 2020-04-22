FAT32
=====

Автор: Пережогин Евгений
Пример запуска:
python3.6 fat32.py /dev/sda1



Управление
==========

Доступны команды:

load - загрузить другой образ
ls - список файлов (help по параметрам)
cat - вывод текста файла (по умолчанию в LATIN-1)
hd - шестнадцатиричное представление файла
cd - смена директории
export - копирование файла образа на диск
import - копирование файла с диска в образ
md - создание директории
cf - создание файла
rm - удаление файла или директории (рекурсивно)



Образы
======

В папке tests лежит сценарий __init__.py, исполнив который появятся образы
при наличии Интернет соединения. При запуске тестов они скачаются и удалятся.