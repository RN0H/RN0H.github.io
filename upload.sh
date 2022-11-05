#!/bin/bash

_upload_(){
    echo args
    git add .
    git commit -m args
    git push origin master
}

args = "$@"
_upload_ args