#!/bin/bash

_upload_(){
    echo "$1"
    git add .
    git commit -m "$1"
    git push origin master
}

_upload_ $1