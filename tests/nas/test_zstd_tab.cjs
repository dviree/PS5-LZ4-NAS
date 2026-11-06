// Run with node tests/nas/test_zstd_tab.cjs; no dependencies.
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = readFileSync(require('node:path').join(__dirname, '../../nas-lz4/ui.html'), 'utf8');
for (const [, script] of html.matchAll(/<script>([\s\S]*?)<\/script>/g)) new vm.Script(script);
const elements = new Map();
const document = {getElementById: id => {
  if (!elements.has(id)) elements.set(id, {value: '', checked: true, innerHTML: '', textContent: ''});
  return elements.get(id);
}};
let request;
const context = vm.createContext({document, esc: s => String(s ?? '').replaceAll('<', '&lt;'),
  gb: n => String(n), pendingFor: id => id === 'pending',
  compress: (...args) => {request = args;}});
vm.runInContext(html.slice(html.indexOf('function renderZstd()'), html.indexOf("let packMode = 'legacy'")), context);
context.data = {zstd_output_host: '/volume1/games/ps5zstd', games: [
  {id: 'source', name: '<Source>', title_id: 'PPSA00001', pack_codec: 'lz4', output: '/lz4/source'},
  {id: 'ready', name: 'Ready', pack_codec: 'zstd', output: '/zstd/ready', output_bytes: 100},
  {id: 'pending', name: 'Pending'}, {id: 'queued', name: 'Queued', queued: true},
  {id: 'running', name: 'Running', running: true},
  {id: 'lz4-only', name: 'LZ4 only', pack_codec: 'lz4', output_only: true},
  {id: 'zstd-only', name: 'Zstd only', pack_codec: 'zstd', output_only: true, output: '/zstd/only'},
]};
vm.runInContext('renderZstd()', context);
let list = document.getElementById('zstd-games').innerHTML;
assert.ok(list.includes('&lt;Source>'));
assert.ok(!list.includes('LZ4 only'));
assert.ok(list.includes('Zstd only'));
assert.equal((list.match(/Compress to Zstd/g) || []).length, 1);
assert.ok(list.includes('waiting to start') && list.includes('queued') && list.includes('packing'));
assert.equal(document.getElementById('zstd-output').textContent, '/volume1/games/ps5zstd');
document.getElementById('zstd-q').value = 'ppsa00001';
vm.runInContext('renderZstd()', context);
assert.ok(document.getElementById('zstd-games').innerHTML.includes('&lt;Source>'));
assert.ok(!document.getElementById('zstd-games').innerHTML.includes('Ready'));
document.getElementById('zstd-level').value = '12';
document.getElementById('zstd-profile').checked = false;
vm.runInContext("compressZstd('source', true)", context);
assert.deepEqual(JSON.parse(JSON.stringify(request)), ['source', true, false,
  {codec: 'zstd', runtime: 'ng', level: 12, profile: false}]);
assert.ok(html.includes("'#zstd': 'zstd'"));
assert.ok(html.includes("['mine', 'zstd', 'act'"));
console.log('Zstd tab tests passed');

(async () => {
  context.closeGame = () => {};
  context.tab = () => {};
  const editor = document.getElementById('profile-editor');
  editor.dataset = {};
  editor.scrollIntoView = () => {};
  let saved;
  context.fetch = async (url, options) => {
    if (options?.method === 'POST') {
      saved = JSON.parse(options.body);
      return {ok: true, json: async () => ({description: 'Saved'})};
    }
    return {ok: true, json: async () => ({name: 'Game', content: '[pack]', description: 'custom'})};
  };
  await vm.runInContext("openProfile('source')", context);
  assert.equal(editor.dataset.game, 'source');
  assert.equal(document.getElementById('profile-content').value, '[pack]');
  const input = {files: [{name: 'game.toml', size: 40, text: async () => '[pack]\ndefault_action="loose"'}]};
  context.input = input;
  await vm.runInContext('importProfile(input)', context);
  vm.runInContext('renderZstd()', context);
  assert.equal(document.getElementById('profile-content').value, '[pack]\ndefault_action="loose"');
  await vm.runInContext('saveProfile()', context);
  assert.deepEqual(saved, {action: 'profile_save', game: 'source', content: '[pack]\ndefault_action="loose"'});
  context.fetch = async () => ({ok: false, json: async () => ({error: 'invalid TOML'})});
  await vm.runInContext('saveProfile()', context);
  assert.ok(document.getElementById('profile-msg').textContent.includes('invalid TOML'));
  assert.equal(document.getElementById('profile-save').disabled, false);
  console.log('TOML editor tests passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
