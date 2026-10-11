// Full-screen action pages, history, about, and the splash / done overlays.
import {useEffect, useRef, useState} from 'react';
import {View, Text, Image, ScrollView, FocusScope} from '@ps5-react/core';
import {api, iconUrl} from './api.js';
import {ACTION_LABEL, formatBytes, kindLabel, readableError, opSummary, opTime, opTone, resultText, storageLabel} from './model.js';
import {ActionRow, Choice, Dot, LevelScale, LOGO, PrimaryButton, SectionLabel} from './ui.jsx';

export function Page({title, depth, covered, hide, onBack, children}) {
  return (
    <FocusScope autoFocus restoreFocus focusKey={'screen-' + depth} inert={covered}
      onBack={() => { onBack(); return true; }}>
      <View className={hide ? 'hidden' : 'absolute inset-0 bg-ink'}>
        <View className="px-[48px] pt-[36px] pb-2">
          <Text className="font-heavy text-[28px] text-snow" numberOfLines={1}>{title}</Text>
        </View>
        <ScrollView className="flex-1">
          <View className="px-[48px] pb-[64px]">{children}</View>
        </ScrollView>
      </View>
    </FocusScope>
  );
}

function Row({children}) {
  return <View className="flex-row flex-wrap gap-4">{children}</View>;
}

function useUsb() {
  const [usb, setUsb] = useState([]);
  useEffect(() => {
    let live = true;
    api.usb().then(data => { if (live) setUsb(data.usb || []); }).catch(() => {});
    return () => { live = false; };
  }, []);
  return usb;
}

function usbDesc(target) {
  return `${target.targetRoot || target.root}  ·  ${formatBytes(target.freeBytes)} free`;
}

const onData = game => String(game.sourcePath || '').startsWith('/data/');

const whereText = where => (where === 'Import folder' ? 'in the import folder' : `on ${where}`);

// ---------------------------------------------------------------- compress / make image

export function CompressPage({game, action, depth, covered, hide, onBack, onStart}) {
  const usb = useUsb();
  const makeImage = action === 'make-image';
  const [format, setFormat] = useState('exfat');
  const [dest, setDest] = useState('keep');
  const [usbId, setUsbId] = useState('');
  const [handling, setHandling] = useState(makeImage ? 'keep' : 'after');
  const elsewhere = dest !== 'keep';
  const canStream = !makeImage && !elsewhere && game.canStreamDelete === true;
  const policy = handling === 'keep' ? 'keep' : elsewhere ? 'after' : handling;
  const start = () => onStart(() => api.compress(game, {
    action, format, destination: dest === 'usb' ? 'usb' : dest, deletePolicy: policy, usbId: dest === 'usb' ? usbId : '',
  }), makeImage ? 'Making image' : 'Compressing');
  return (
    <Page title={`${ACTION_LABEL[action]}  ·  ${game.name || game.titleId}`}
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      <SectionLabel>{makeImage ? 'Image format' : 'Inner image format'}</SectionLabel>
      <Row>
        <Choice title="exFAT" desc="Recommended" selected={format === 'exfat'} onPress={() => setFormat('exfat')} autoFocus />
        <Choice title="PFS" desc="Experimental" selected={format === 'pfs'} onPress={() => setFormat('pfs')} />
      </Row>
      <SectionLabel>Destination</SectionLabel>
      <Row>
        <Choice title="Next to the game" desc={storageLabel(game)} selected={dest === 'keep'} onPress={() => setDest('keep')} />
        {!onData(game) ? <Choice title="Internal SSD" desc="/data/homebrew" selected={dest === 'internal'}
          onPress={() => setDest('internal')} /> : null}
        {usb.map(target => (
          <Choice key={target.id} title={target.name || 'USB'} desc={usbDesc(target)}
            selected={dest === 'usb' && usbId === target.id} onPress={() => { setDest('usb'); setUsbId(target.id); }} />
        ))}
      </Row>
      <SectionLabel>Original</SectionLabel>
      <Row>
        <Choice title="Keep original" desc="Leave the source untouched" selected={handling === 'keep'} onPress={() => setHandling('keep')} />
        <Choice title="Delete after verified" desc="Needs room for the full output first" selected={handling === 'after'}
          onPress={() => setHandling('after')} />
        <Choice title="Destructive" desc="Needs 1 GB free; can't be cancelled once it starts" selected={handling === 'stream'}
          disabled={!canStream} onPress={() => setHandling('stream')} />
      </Row>
      <View className="mt-8 flex-row"><PrimaryButton label={ACTION_LABEL[action]} onPress={start} focusKey="start" /></View>
    </Page>
  );
}

// ---------------------------------------------------------------- LZ4 pack / unpack

export function Lz4Page({game, mode, depth, covered, hide, onBack, onStart, onImport, profileRev}) {
  const usb = useUsb();
  const unpack = mode === 'unpack';
  const folder = String(game.sourceKind || '') === 'folder';
  const [level, setLevel] = useState(9);
  const [profile, setProfile] = useState('auto');
  const [profileInfo, setProfileInfo] = useState(null);
  const [match, setMatch] = useState(null);
  const [dest, setDest] = useState('inplace');
  const [usbId, setUsbId] = useState('');
  const [policy, setPolicy] = useState('after');
  const [refresh, setRefresh] = useState(0);
  const profileReady = !!(profileInfo && profileInfo.exists) &&
    !(profileInfo.includes || []).some(item => !item.present);
  useEffect(() => {
    if (unpack) return undefined;
    let live = true;
    api.lz4Profile(game).then(info => {
      if (!live) return;
      setProfileInfo(info);
      const ready = !!info.exists && !(info.includes || []).some(item => !item.present);
      // The game's own imported config wins, then the bundled pick (Automatic).
      setProfile(ready ? 'custom' : 'auto');
    }).catch(() => {});
    api.lz4Configs(game).then(data => {
      if (live) setMatch((data.configs || []).find(item => item.match) || null);
    }).catch(() => {});
    return () => { live = false; };
  }, [game.titleId, unpack, profileRev, refresh]);
  const removeProfile = () => {
    api.removeProfile(game).then(() => setRefresh(value => value + 1)).catch(() => {});
  };
  const missing = profileInfo && profileInfo.exists ? (profileInfo.includes || []).filter(item => !item.present) : [];
  const customDesc = profileReady ? 'Imported config for this game'
    : missing.length ? `Missing ${missing.map(item => item.name).join(', ')}` : 'Import a TOML config first';
  const auto = game.lz4AutoProfile;
  const autoDesc = auto ? `${auto.label} profile, tested on ${auto.tested}`
    : 'Scans the game and keeps executables, system files and media loose';
  const canReplace = folder && dest === 'inplace';
  const chosenPolicy = !canReplace && policy === 'replace' ? 'after' : policy;
  const start = () => onStart(() => api.lz4(game, {
    mode: unpack ? 'unpack' : 'pack', level: String(level), profile, destination: dest, deletePolicy: chosenPolicy, usbId,
  }), unpack ? 'Unpacking LZ4' : 'Packing with LZ4');
  return (
    <Page title={`${unpack ? 'Uncompress LZ4' : 'Compress with LZ4'}  ·  ${game.name || game.titleId}`}
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      {!unpack ? (
        <>
          <SectionLabel>Compression level</SectionLabel>
          <LevelScale value={level} onChange={setLevel} autoFocus />
          <SectionLabel>Packing profile</SectionLabel>
          <Row>
            <Choice title="Automatic" desc={autoDesc} wide selected={profile === 'auto'} onPress={() => setProfile('auto')} />
            {auto ? <Choice title="Scan only" desc="Skip the bundled profile and scan the game" wide selected={profile === 'scan'}
              onPress={() => setProfile('scan')} /> : null}
            <Choice title="Custom or trace config" wide desc={customDesc}
              selected={profile === 'custom'} disabled={!profileReady} onPress={() => setProfile('custom')} />
            <ActionRow title="Import config" icon="download" onPress={onImport} focusKey="import-config"
              desc={match ? `Found ${match.name} ${whereText(match.where)}` : 'A Lazy_AMPR or ampr_pack TOML from USB or the import folder'} />
            {profileInfo && profileInfo.exists ? (
              <ActionRow title="Remove config" icon="trash" onPress={removeProfile} focusKey="remove-config"
                desc="Go back to automatic packing for this game" />
            ) : null}
          </Row>
        </>
      ) : null}
      <SectionLabel>Destination</SectionLabel>
      <Row>
        <Choice title={unpack ? 'In place' : 'Next to the game'} desc={storageLabel(game)} selected={dest === 'inplace'}
          onPress={() => setDest('inplace')} autoFocus={unpack} />
        {!onData(game) ? <Choice title="Internal SSD" desc="/data/homebrew" selected={dest === 'internal'}
          onPress={() => setDest('internal')} /> : null}
        {usb.map(target => (
          <Choice key={target.id} title={target.name || 'USB'} desc={usbDesc(target)}
            selected={dest === 'usb' && usbId === target.id} onPress={() => { setDest('usb'); setUsbId(target.id); }} />
        ))}
      </Row>
      <SectionLabel>Original</SectionLabel>
      <Row>
        <Choice title="Keep original" desc="Leave the source untouched" selected={chosenPolicy === 'keep'} onPress={() => setPolicy('keep')} />
        <Choice title="Delete after verified" desc="Needs room for the full output first" selected={chosenPolicy === 'after'}
          onPress={() => setPolicy('after')} />
        <Choice title="In place" desc={unpack ? 'Unpacks inside the folder' : 'Verified first, needs the least space'}
          selected={chosenPolicy === 'replace'} disabled={!canReplace} onPress={() => setPolicy('replace')} />
      </Row>
      <View className="mt-8 flex-row"><PrimaryButton label={unpack ? 'Uncompress LZ4' : 'Compress with LZ4'} onPress={start} focusKey="start" /></View>
    </Page>
  );
}

// ---------------------------------------------------------------- import config

export function ConfigPage({game, depth, covered, hide, onBack, onImported}) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    let live = true;
    api.lz4Configs(game).then(result => { if (live) setData(result); })
      .catch(err => { if (live) { setData({configs: []}); setError(err.message || ''); } });
    return () => { live = false; };
  }, [game.titleId]);
  const pick = config => {
    if (busy) return;
    setBusy(config.path);
    setError('');
    api.importConfig(game, config.path).then(() => onImported(config.name))
      .catch(err => { setBusy(''); setError(err.message || 'Import failed'); });
  };
  const configs = data ? data.configs || [] : [];
  return (
    <Page title={`Import config  ·  ${game.name || game.titleId}`}
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      {!data ? <Text className="font-inter text-[14px] text-muted mt-6">Looking for configs</Text> : null}
      {data && !configs.length ? (
        <View className="mt-6 gap-2 w-[760px]">
          <Text className="font-semi text-[16px] text-snow">No TOML configs found</Text>
          <Text className="font-inter text-[14px] text-soft">
            {`Looked in ${data.importDir || '/data/LZ4Compression/import'} and on USB drives (top folder, toml, toml_profiles).`}
          </Text>
        </View>
      ) : null}
      {configs.some(item => item.match) ? <SectionLabel>Matches this game</SectionLabel> : null}
      <Row>
        {configs.filter(item => item.match).map((config, index) => (
          <ActionRow key={config.path} title={config.name} icon="download" autoFocus={index === 0} focusKey={'config-' + config.path}
            desc={busy === config.path ? 'Importing' : `${config.where}  ·  ${formatBytes(config.size)}`} onPress={() => pick(config)} />
        ))}
      </Row>
      {configs.some(item => !item.match) ? <SectionLabel>Other configs</SectionLabel> : null}
      <Row>
        {configs.filter(item => !item.match).map((config, index) => (
          <ActionRow key={config.path} title={config.name} icon="list" focusKey={'config-' + config.path}
            autoFocus={index === 0 && !configs.some(item => item.match)}
            desc={busy === config.path ? 'Importing' : `${config.where}  ·  ${formatBytes(config.size)}`} onPress={() => pick(config)} />
        ))}
      </Row>
      {error ? <Text className="font-inter text-[14px] text-bad mt-6">{error}</Text> : null}
    </Page>
  );
}

// ---------------------------------------------------------------- uncompress

export function UncompressPage({game, depth, covered, hide, onBack, onStart}) {
  const usb = useUsb();
  const [mode, setMode] = useState('image');
  const [dest, setDest] = useState('inplace');
  const [usbId, setUsbId] = useState('');
  const [policy, setPolicy] = useState('keep');
  const [plan, setPlan] = useState(null);
  const picked = useRef(false);
  useEffect(() => {
    let live = true;
    api.uncompressPlan(game).then(data => { if (live) setPlan(data); }).catch(() => {});
    return () => { live = false; };
  }, [game.titleId, game.sourcePath]);
  // The uncompressed game is far bigger than the .ffpfsc: show what each place has room for.
  const need = plan ? plan.requiredBytes || 0 : 0;
  const fits = free => !need || !free || free >= need;
  const room = free => (fits(free) ? `${formatBytes(free)} free` : `Needs ${formatBytes(need)}, ${formatBytes(free)} free`);
  const hereFree = plan ? plan.freeBytes || 0 : 0;
  useEffect(() => {
    if (picked.current || !plan || fits(hereFree)) return;
    const target = usb.find(item => fits(item.freeBytes));
    if (target) { setDest('usb'); setUsbId(target.id); }
  }, [plan, usb]);
  const pick = (next, id) => { picked.current = true; setDest(next); setUsbId(id || ''); };
  const sized = text => (need ? `${text}  ·  ${formatBytes(need)}` : text);
  const start = () => onStart(() => api.uncompress(game, {
    mode: mode === 'image' ? 'image' : 'app', destination: dest, deletePolicy: policy, usbId: dest === 'usb' ? usbId : '',
  }), 'Uncompressing');
  return (
    <Page title={`Uncompress  ·  ${game.name || game.titleId}`}
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      <SectionLabel>Output</SectionLabel>
      <Row>
        <Choice title="Image" desc={sized('The image inside the .ffpfsc')} selected={mode === 'image'} onPress={() => setMode('image')} autoFocus />
        <Choice title="Game folder" desc={sized('Loose files')} selected={mode === 'app'} onPress={() => setMode('app')} />
      </Row>
      <SectionLabel>Destination</SectionLabel>
      <Row>
        <Choice title="In place" desc={hereFree ? `${storageLabel(game)}  ·  ${room(hereFree)}` : storageLabel(game)}
          selected={dest === 'inplace'} disabled={!fits(hereFree)} onPress={() => pick('inplace')} />
        {!onData(game) ? <Choice title="Internal SSD" desc="/data/homebrew" selected={dest === 'internal'}
          onPress={() => pick('internal')} /> : null}
        {usb.map(target => (
          <Choice key={target.id} title={target.name || 'USB'}
            desc={`${target.targetRoot || target.root}  ·  ${room(target.freeBytes)}`} disabled={!fits(target.freeBytes)}
            selected={dest === 'usb' && usbId === target.id} onPress={() => pick('usb', target.id)} />
        ))}
      </Row>
      <SectionLabel>Compressed image</SectionLabel>
      <Row>
        <Choice title="Keep both" desc="Leave the .ffpfsc after the output is ready" selected={policy === 'keep'} onPress={() => setPolicy('keep')} />
        <Choice title="Delete after" desc="Remove the .ffpfsc once the output is ready" selected={policy === 'after'} onPress={() => setPolicy('after')} />
      </Row>
      <View className="mt-8 flex-row"><PrimaryButton label="Uncompress" onPress={start} focusKey="start" /></View>
    </Page>
  );
}

// ---------------------------------------------------------------- copy / move

export function MovePage({game, copy, depth, covered, hide, onBack, onStart}) {
  const usb = useUsb();
  const verb = copy ? 'Copy' : 'Move';
  const go = (target, usbId) => onStart(() => api.move(game, {copy, target, usbId}), copy ? 'Copying' : 'Moving');
  return (
    <Page title={`${verb} to…  ·  ${game.name || game.titleId}`}
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      <SectionLabel>Where to</SectionLabel>
      <View className="gap-4">
        {game.canMoveToInternal ? <Choice wide title="Internal SSD" desc="/data/homebrew" onPress={() => go('internal', '')} autoFocus /> : null}
        {game.canMoveToUsb ? usb.map((target, index) => (
          <Choice wide key={target.id} title={target.name || 'USB'} desc={usbDesc(target)}
            onPress={() => go('usb', target.id)} autoFocus={!game.canMoveToInternal && index === 0} />
        )) : null}
        {!game.canMoveToInternal && !(game.canMoveToUsb && usb.length) ? (
          <Text className="font-inter text-[14px] text-muted">No other storage to use right now.</Text>
        ) : null}
      </View>
    </Page>
  );
}

// ---------------------------------------------------------------- delete

export function DeletePage({game, depth, covered, hide, onBack, onStart}) {
  return (
    <Page title="Delete game data"
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      <View className="mt-6 p-6 rounded-[20px] border-2 border-bad bg-[#1d070c] gap-2 w-[760px]">
        <Text className="font-heavy text-[20px] text-snow">{game.name || game.titleId}</Text>
        <Text className="font-inter text-[13px] text-soft">{`${kindLabel(game)}  ·  ${storageLabel(game)}`}</Text>
        <Text className="font-inter text-[12px] text-muted" numberOfLines={2}>{game.sourcePath}</Text>
        <Text className="font-semi text-[13px] text-bad mt-2">This can't be undone.</Text>
      </View>
      <View className="flex-row gap-4 mt-8">
        <PrimaryButton label="Cancel" onPress={onBack} autoFocus />
        <PrimaryButton label="Delete" danger onPress={() => onStart(() => api.deleteGame(game), 'Deleting')} />
      </View>
    </Page>
  );
}

// ---------------------------------------------------------------- history

function when(seconds) {
  if (!seconds) return '';
  const date = new Date(seconds * 1000);
  return `${String(date.getDate()).padStart(2, '0')}/${String(date.getMonth() + 1).padStart(2, '0')} ` +
    `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

export function HistoryPage({history, depth, covered, hide, onBack}) {
  return (
    <Page title="History">
      <View className="gap-3 mt-4">
        {history.length ? history.map((op, index) => (
          <View key={op.id} focusable autoFocus={index === 0}
            className="flex-row items-center gap-4 w-[1180px] px-5 py-4 rounded-[16px] bg-panel border border-line focused:border-snow">
            <View className="flex-1 gap-1">
              <Text className="font-semi text-[15px] text-snow" numberOfLines={1}>{op.displayName || op.titleId}</Text>
              <Text className="font-inter text-[12px] text-soft" numberOfLines={1}>{opSummary(op)}</Text>
              {op.error ? <Text className="font-inter text-[12px] text-bad" numberOfLines={2}>{readableError(op.error)}</Text> : null}
            </View>
            <Text className="font-inter text-[12px] text-muted">{when(opTime(op))}</Text>
            <View className="flex-row items-center gap-2 w-[150px]">
              <Dot tone={opTone(op)} />
              <Text className="font-semi text-[13px] text-snow">{resultText(op)}</Text>
            </View>
          </View>
        )) : <Text className="font-inter text-[14px] text-muted">No jobs yet.</Text>}
      </View>
    </Page>
  );
}

// ---------------------------------------------------------------- about / power

export function AboutPage({version, depth, covered, hide, onBack}) {
  return (
    <Page title="About" depth={depth} covered={covered} hide={hide} onBack={onBack}>
      <View focusable autoFocus className="items-center gap-4 mt-6 w-[1180px]">
        <Image source={LOGO} className="w-[128px] h-[128px] rounded-[30px]" />
        <Text className="font-heavy text-[30px] text-snow">LZ4 Compression</Text>
        <Text className="font-inter text-[14px] text-muted">{version || ''}</Text>
        <View className="mt-4 p-5 rounded-[18px] border border-line bg-panel w-[760px]">
          <Text className="font-inter text-[12px] text-muted">
            Built on Game Compressor by Juma Sayeh and the LZ4 workflow from Lazy_AMPR by Nazky. Packed games are read by drakmor's ampr_emu. Unofficial, and not affiliated with either project. Interface made with PS5 React, created by half144 and PS5 React contributors (github.com/half144/ps5-react).
          </Text>
        </View>
      </View>
    </Page>
  );
}

export function PowerPage({depth, covered, hide, onBack, onStop}) {
  return (
    <Page title="Close LZ4 Compression"
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      <View className="flex-row gap-4 mt-8">
        <PrimaryButton label="Stop engine and close" onPress={() => onStop(true)} autoFocus />
        <PrimaryButton label="Close app only" onPress={() => onStop(false)} />
      </View>
    </Page>
  );
}

// ---------------------------------------------------------------- splash, offline, done, toast

export function Splash({status}) {
  return (
    <View className="w-screen h-screen bg-ink items-center justify-center gap-6">
      <Image source={LOGO} className="w-[132px] h-[132px] rounded-[30px] animate-in zoom-in-95 fade-in duration-500" />
      <Text className="font-heavy text-[34px] text-snow">LZ4 Compression</Text>
      <View className="w-[200px] h-[4px] rounded-full bg-line overflow-hidden">
        <View className="w-[40%] h-[4px] rounded-full bg-snow animate-pulse" />
      </View>
      <Text className="font-inter text-[13px] text-muted">{status}</Text>
    </View>
  );
}

export function Offline({message, onStart, onRetry}) {
  return (
    <FocusScope autoFocus trap>
      <View className="w-screen h-screen bg-ink items-center justify-center gap-5">
        <Image source={LOGO} className="w-[110px] h-[110px] rounded-[26px] opacity-70" />
        <Text className="font-heavy text-[28px] text-snow">The engine isn't running</Text>
        {message ? <Text className="font-inter text-[14px] text-muted w-[720px] text-center">{message}</Text> : null}
        <View className="flex-row gap-4 mt-4">
          <PrimaryButton label="Start engine" onPress={onStart} autoFocus />
          <PrimaryButton label="Try again" onPress={onRetry} />
        </View>
      </View>
    </FocusScope>
  );
}

export function DoneOverlay({op, game, onClose}) {
  const ok = String(op.status) === 'success';
  const icon = game ? iconUrl(game, false) : '';
  return (
    <FocusScope autoFocus trap onBack={() => { onClose(); return true; }}>
      <View className="absolute inset-0 bg-ink/90 items-center justify-center">
        <View className="w-[560px] items-center gap-3 p-8 rounded-[28px] bg-panel border border-line animate-in zoom-in-95 fade-in duration-300">
          {icon ? <Image source={{uri: icon}} className="w-[112px] h-[112px] rounded-[26px] bg-raised" />
            : <Image source={LOGO} className="w-[112px] h-[112px] rounded-[26px]" />}
          <Text className="font-heavy text-[30px] text-snow">{ok ? 'Done' : 'Something went wrong'}</Text>
          <Text className="font-inter text-[15px] text-soft text-center" numberOfLines={2}>{op.displayName || op.titleId}</Text>
          <Text className="font-inter text-[14px] text-soft text-center" numberOfLines={2}>{opSummary(op)}</Text>
          {op.error ? <Text className="font-inter text-[13px] text-bad text-center" numberOfLines={3}>{readableError(op.error)}</Text> : null}
          <View className="mt-3"><PrimaryButton label="OK" onPress={onClose} autoFocus /></View>
        </View>
      </View>
    </FocusScope>
  );
}

export function Toast({toast}) {
  if (!toast) return null;
  if (toast.error) {
    return (
      <View className="absolute right-[48px] top-[90px] w-[440px] p-4 rounded-[16px] bg-[#2a0d13] border border-bad animate-in fade-in slide-in-from-right-4">
        <Text className="font-semi text-[14px] text-snow">{toast.title}</Text>
        {toast.text ? <Text className="font-inter text-[12px] text-soft mt-1" numberOfLines={3}>{toast.text}</Text> : null}
      </View>
    );
  }
  return (
    <View className="absolute right-[48px] top-[90px] w-[440px] p-4 rounded-[16px] bg-raised border border-line animate-in fade-in slide-in-from-right-4">
      <Text className="font-semi text-[14px] text-snow">{toast.title}</Text>
      {toast.text ? <Text className="font-inter text-[12px] text-soft mt-1" numberOfLines={3}>{toast.text}</Text> : null}
    </View>
  );
}
