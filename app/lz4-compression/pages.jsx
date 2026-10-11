// Full-screen action pages, history, about, and the splash / done overlays.
import {useEffect, useState} from 'react';
import {View, Text, Image, ScrollView, FocusScope} from '@ps5-react/core';
import {api, iconUrl} from './api.js';
import {ACTION_LABEL, formatBytes, kindLabel, opSummary, opTime, opTone, resultText, storageLabel} from './model.js';
import {Choice, Dot, LOGO, PrimaryButton, SectionLabel} from './ui.jsx';

export function Page({title, subtitle, depth, covered, hide, onBack, children}) {
  return (
    <FocusScope autoFocus restoreFocus focusKey={'screen-' + depth} inert={covered}
      onBack={() => { onBack(); return true; }}>
      <View className={hide ? 'hidden' : 'absolute inset-0 bg-ink'}>
        <View className="px-[48px] pt-[36px] pb-2 gap-1">
          <Text className="font-heavy text-[28px] text-snow" numberOfLines={1}>{title}</Text>
          {subtitle ? <Text className="font-inter text-[14px] text-muted" numberOfLines={1}>{subtitle}</Text> : null}
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
      subtitle={makeImage ? 'Builds a plain image you can mount with ShadowMount+.' : 'Packs the game into a compressed .ffpfsc image.'}
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

export function Lz4Page({game, mode, depth, covered, hide, onBack, onStart}) {
  const usb = useUsb();
  const unpack = mode === 'unpack';
  const folder = String(game.sourceKind || '') === 'folder';
  const [level, setLevel] = useState('balanced');
  const [profile, setProfile] = useState('auto');
  const [profileReady, setProfileReady] = useState(false);
  const [dest, setDest] = useState('inplace');
  const [usbId, setUsbId] = useState('');
  const [policy, setPolicy] = useState('after');
  useEffect(() => {
    if (unpack) return undefined;
    let live = true;
    api.lz4Profile(game).then(info => {
      const ready = !!info.exists && !(info.includes || []).some(item => !item.present);
      if (live) setProfileReady(ready);
    }).catch(() => {});
    return () => { live = false; };
  }, [game.titleId, unpack]);
  const canReplace = folder && dest === 'inplace';
  const chosenPolicy = !canReplace && policy === 'replace' ? 'after' : policy;
  const start = () => onStart(() => api.lz4(game, {
    mode: unpack ? 'unpack' : 'pack', level, profile, destination: dest, deletePolicy: chosenPolicy, usbId,
  }), unpack ? 'Unpacking LZ4' : 'Packing with LZ4');
  return (
    <Page title={`${unpack ? 'Uncompress LZ4' : 'Compress with LZ4'}  ·  ${game.name || game.titleId}`}
      subtitle={unpack ? 'Puts the normal loose files back from the LZ4 packs.'
        : 'Seekable LZ4 packs that APR-EMU reads while the game runs. Every packed file is checked against the original.'}
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      {!unpack ? (
        <>
          <SectionLabel>Level</SectionLabel>
          <Row>
            <Choice title="Fast" desc="LZ4, quickest" selected={level === 'fast'} onPress={() => setLevel('fast')} />
            <Choice title="Balanced" desc="LZ4 HC 9, recommended" selected={level === 'balanced'} onPress={() => setLevel('balanced')} autoFocus />
            <Choice title="Maximum" desc="LZ4 HC 12, smallest and slowest" selected={level === 'max'} onPress={() => setLevel('max')} />
          </Row>
          <SectionLabel>Packing profile</SectionLabel>
          <Row>
            <Choice title="Automatic" desc="Keeps executables, system files and media loose" wide selected={profile === 'auto'}
              onPress={() => setProfile('auto')} />
            <Choice title="Custom or trace profile" wide
              desc={profileReady ? 'Uploaded profile for this game' : 'Upload one from a PC or phone at port 5920'}
              selected={profile === 'custom'} disabled={!profileReady} onPress={() => setProfile('custom')} />
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

// ---------------------------------------------------------------- uncompress

export function UncompressPage({game, depth, covered, hide, onBack, onStart}) {
  const usb = useUsb();
  const [mode, setMode] = useState('image');
  const [dest, setDest] = useState('inplace');
  const [usbId, setUsbId] = useState('');
  const [policy, setPolicy] = useState('keep');
  const start = () => onStart(() => api.uncompress(game, {
    mode: mode === 'image' ? 'image' : 'app', destination: dest, deletePolicy: policy, usbId: dest === 'usb' ? usbId : '',
  }), 'Uncompressing');
  return (
    <Page title={`Uncompress  ·  ${game.name || game.titleId}`} subtitle="Turns the .ffpfsc back into a plain image or a game folder."
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      <SectionLabel>Output</SectionLabel>
      <Row>
        <Choice title="Image" desc="The image inside the .ffpfsc" selected={mode === 'image'} onPress={() => setMode('image')} autoFocus />
        <Choice title="Game folder" desc="Loose files" selected={mode === 'app'} onPress={() => setMode('app')} />
      </Row>
      <SectionLabel>Destination</SectionLabel>
      <Row>
        <Choice title="In place" desc={storageLabel(game)} selected={dest === 'inplace'} onPress={() => setDest('inplace')} />
        {!onData(game) ? <Choice title="Internal SSD" desc="/data/homebrew" selected={dest === 'internal'}
          onPress={() => setDest('internal')} /> : null}
        {usb.map(target => (
          <Choice key={target.id} title={target.name || 'USB'} desc={usbDesc(target)}
            selected={dest === 'usb' && usbId === target.id} onPress={() => { setDest('usb'); setUsbId(target.id); }} />
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
      subtitle={copy ? 'Makes a second copy somewhere else.' : 'Moves the game and removes it from here once it is copied.'}
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
    <Page title="Delete game data" subtitle="This permanently deletes this copy from storage. It can't be undone."
      depth={depth} covered={covered} hide={hide} onBack={onBack}>
      <View className="mt-6 p-6 rounded-[20px] border-2 border-bad bg-[#1d070c] gap-2 w-[760px]">
        <Text className="font-heavy text-[20px] text-snow">{game.name || game.titleId}</Text>
        <Text className="font-inter text-[13px] text-soft">{`${kindLabel(game)}  ·  ${storageLabel(game)}`}</Text>
        <Text className="font-inter text-[12px] text-muted" numberOfLines={2}>{game.sourcePath}</Text>
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
    <Page title="History" subtitle={`${history.length} jobs`} depth={depth} covered={covered} hide={hide} onBack={onBack}>
      <View className="gap-3 mt-4">
        {history.length ? history.map((op, index) => (
          <View key={op.id} focusable autoFocus={index === 0}
            className="flex-row items-center gap-4 w-[1180px] px-5 py-4 rounded-[16px] bg-panel border border-line focused:border-snow">
            <View className="flex-1 gap-1">
              <Text className="font-semi text-[15px] text-snow" numberOfLines={1}>{op.displayName || op.titleId}</Text>
              <Text className="font-inter text-[12px] text-soft" numberOfLines={1}>{opSummary(op)}</Text>
              {op.error ? <Text className="font-inter text-[12px] text-bad" numberOfLines={2}>{op.error}</Text> : null}
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
        <Text className="font-inter text-[15px] text-soft">LZ4 compression for APR-EMU games, done right on the PS5.</Text>
        <Text className="font-inter text-[13px] text-muted">Upload LZ4 profiles from a PC or phone: open your PS5's IP on port 5920.</Text>
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
    <Page title="Close LZ4 Compression" subtitle="Stop the engine before you play, so it doesn't take anything away from your games."
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
        <Text className="font-inter text-[14px] text-muted w-[720px] text-center">
          {message || 'Load lz4-compression.elf from Payload Manager, or let the app start it for you.'}
        </Text>
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
          {op.error ? <Text className="font-inter text-[13px] text-bad text-center" numberOfLines={3}>{op.error}</Text> : null}
          {ok ? <Text className="font-inter text-[12px] text-muted text-center">
            Before playing, close LZ4 Compression so it doesn't take anything away from your games.
          </Text> : null}
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
