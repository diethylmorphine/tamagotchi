// Slice generated transparent atlases into consistently aligned runtime sprites.
// Usage: NODE_PATH=<directory containing sharp> node scripts/prepare_pet_assets.cjs
const sharp = require('sharp');
const fs = require('node:fs/promises');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const emotions = ['calm', 'happy', 'sleeping', 'sad', 'hungry', 'grumpy'];

(async () => {
  const destination = path.join(root, 'frontend/assets/pets');
  await fs.mkdir(destination, {recursive: true});
  for (const species of ['fox', 'cat', 'snow_leopard', 'snake']) {
    const source = path.join(root, `output/pet-emotions/${species}-atlas.png`);
    // A species without a generated atlas keeps its current sprites.
    if (!await fs.access(source).then(() => true, () => false)) { console.log(`skip ${species}: no atlas`); continue; }
    const {width, height, hasAlpha} = await sharp(source).metadata();
    if (!hasAlpha || width !== height) throw new Error('Unexpected atlas format');
    // Atlases are laid out in even thirds; cuts stay in the empty gutters.
    const unit = width / 1254; // Cut positions below were measured on 1254px atlases.
    const columns = [0, 418, 836, 1254].map(x => Math.round(x * unit));
    const pieces = [];
    for (let index = 0; index < 6; index++) {
      const col = index % 3;
      const cell = await sharp(source).extract({
        left: columns[col], top: index < 3 ? 0 : Math.round(627 * unit),
        width: columns[col + 1] - columns[col], height: Math.round(627 * unit),
      }).png().toBuffer();
      const {data, info} = await sharp(cell)
        .trim({background: '#00000000', threshold: 20}).png().toBuffer({resolveWithObject: true});
      pieces.push({data, info});
    }
    const scale = Math.min(450 / Math.max(...pieces.map(p => p.info.width)),
      450 / Math.max(...pieces.map(p => p.info.height)));
    for (const [index, piece] of pieces.entries()) {
      const w = Math.round(piece.info.width * scale);
      const h = Math.round(piece.info.height * scale);
      const sprite = await sharp(piece.data).resize(w, h, {kernel: 'nearest'}).toBuffer();
      await sharp({create: {width: 512, height: 512, channels: 4, background: '#00000000'}})
        .composite([{input: sprite, left: Math.floor((512 - w) / 2), top: 480 - h}])
        .webp({lossless: true}).toFile(path.join(destination, `${species}-${emotions[index]}.webp`));
    }
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
