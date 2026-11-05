#!/bin/sh
# Usage: ./set-domain.sh example.com
# Moves the site to a new domain: index.html (links and share-link host) and CNAME,
# then rebuilds en/ ja/ zh/, sitemap.xml and robots.txt from them with build_langs.py.
set -e
cd "$(dirname "$0")"
[ -n "$1" ] || { echo "사용법: ./set-domain.sh 내도메인.com"; exit 1; }
NEW=$(echo "$1" | tr 'A-Z' 'a-z' | sed -e 's#^https*://##' -e 's#/*$##')
echo "$NEW" | grep -Eq '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$' || { echo "도메인 형식이 아니에요: $NEW"; exit 1; }
OLD=$(tr -d ' \n' < CNAME)
OLD_RE=$(printf '%s' "$OLD" | sed 's/\./\\./g')
sed -i '' -e "s#https://$OLD_RE/#https://$NEW/#g" -e "s#const SITE_HOST = \"$OLD_RE\";#const SITE_HOST = \"$NEW\";#" index.html
echo "$NEW" > CNAME
python3 build_langs.py
echo "도메인을 $OLD 에서 $NEW 으로 바꿨어요."
