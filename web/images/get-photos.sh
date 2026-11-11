#!/usr/bin/env bash
# Downloads the app's photos from Unsplash (free to use under the Unsplash License).
# Run from the repo root in Git Bash:   bash web/images/get-photos.sh
# Then look at each photo; replace any you don't like with your own (same file name).
set -euo pipefail
cd "$(dirname "$0")"

get () {  # get <file> <unsplash-photo-id> <width>
  echo "Downloading $1 ..."
  curl -fsSL "https://unsplash.com/photos/$2/download?force=true&w=$3" -o "$1"
}

get hero.jpg          s8Kzx7C6yqo 1800   # African woman pouring harvested grain (Ali Mkumbwa)
get market.jpg        tLZU4kcF058 1200   # Ibadan market, Nigeria (sheyi owolabi)
get maize-white.jpg   _RHIDKQPvhs 800    # Corn cobs (Ioana Cristiana)
get maize-yellow.jpg  a7WVUj_94Go 800    # A pile of corn (Marek Studzinski)
get sorghum-white.jpg 7hxH56RU6zs 800    # Ripe sorghum field (Luis Rodriguez)
get sorghum-red.jpg   5cnyZVI2Eu4 800    # Sorghum crop (Natalia Fogarty)
get soybeans.jpg      AlqMN9ub3Aw 800    # Soy beans close-up (Daniela Paola Alchapar)
get sesame.jpg        NQW68EQnlhg 800    # Sesame seeds (Bjhelyn Igorot Clicker)
get beans.jpg         rZzRWBM7-zw 800    # Black-eyed peas (Jasmine Waheed)
get groundnut.jpg     8LbcvCZnmyw 800    # Bunch of peanuts (Sketch)
get rice-paddy.jpg    _0k7kPHu6hM 800    # Rice husks drying (T. S. W)
# millet.jpg: no good free photo found - the app shows a drawing until you add your own.

echo "Done. Photos saved in $(pwd)"
