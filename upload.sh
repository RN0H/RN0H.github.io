#!/bin/bash

_upload(){
    git add .
    git commit -m "Uploaded using script"
    git push origin master
}
_upload