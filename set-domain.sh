#!/bin/sh
# Usage: ./set-domain.sh minesweeper-kr.com   (fills the domain into the page, robots.txt, sitemap.xml and CNAME)
set -e
[ -n "$1" ] || { echo "사용법: ./set-domain.sh 내도메인.com"; exit 1; }
DOMAIN=$(echo "$1" | sed -e 's#^https*://##' -e 's#/*$##')
sed -i '' "s#__DOMAIN__#$DOMAIN#g" index.html robots.txt sitemap.xml
echo "$DOMAIN" > CNAME
echo "도메인을 $DOMAIN 으로 설정했어요."
