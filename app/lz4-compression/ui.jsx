// Shared building blocks. Layout units are logical px of a 1280x720 screen.
import {memo} from 'react';
import {View, Text, Image, useIsFocused} from '@ps5-react/core';
import logo from './assets/lz4-logo.png';
import iconArrowRight from './assets/icons/arrowRight.png';
import iconBolt from './assets/icons/bolt.png';
import iconCheck from './assets/icons/check.png';
import iconClose from './assets/icons/close.png';
import iconCompress from './assets/icons/compress.png';
import iconCopy from './assets/icons/copy.png';
import iconDisc from './assets/icons/disc.png';
import iconDownload from './assets/icons/download.png';
import iconExpand from './assets/icons/expand.png';
import iconFolder from './assets/icons/folder.png';
import iconGauge from './assets/icons/gauge.png';
import iconHistory from './assets/icons/history.png';
import iconInfo from './assets/icons/info.png';
import iconLayers from './assets/icons/layers.png';
import iconList from './assets/icons/list.png';
import iconLock from './assets/icons/lock.png';
import iconMount from './assets/icons/mount.png';
import iconMove from './assets/icons/move.png';
import iconPower from './assets/icons/power.png';
import iconShield from './assets/icons/shield.png';
import iconTrash from './assets/icons/trash.png';
import iconUndo from './assets/icons/undo.png';
import {TONE_COLOR} from './model.js';

export const LOGO = logo;

const ICONS = {
  arrowRight: iconArrowRight, bolt: iconBolt, check: iconCheck, close: iconClose, compress: iconCompress,
  copy: iconCopy, disc: iconDisc, download: iconDownload, expand: iconExpand, folder: iconFolder,
  gauge: iconGauge, history: iconHistory, info: iconInfo, layers: iconLayers, list: iconList, lock: iconLock,
  mount: iconMount, move: iconMove, power: iconPower, shield: iconShield, trash: iconTrash, undo: iconUndo,
};

// White line icon; dark when its focusable parent is focused (dark=true).
export function Icon({name, size = 'md', dark = false}) {
  const source = ICONS[name] || iconInfo;
  if (size === 'sm') {
    return <Image source={source} className={dark ? 'w-[16px] h-[16px] tint-ink' : 'w-[16px] h-[16px] tint-snow'} />;
  }
  return <Image source={source} className={dark ? 'w-[20px] h-[20px] tint-ink' : 'w-[20px] h-[20px] tint-snow'} />;
}

// Text that turns dark while its focusable parent is focused (white cards).
export function FocusText({children, kind = 'body'}) {
  const focused = useIsFocused();
  if (kind === 'title') {
    return <Text className={focused ? 'font-semi text-[15px] text-ink' : 'font-semi text-[15px] text-snow'}
      numberOfLines={1}>{children}</Text>;
  }
  if (kind === 'button') {
    return <Text className={focused ? 'font-heavy text-[16px] text-ink' : 'font-heavy text-[16px] text-snow'}>{children}</Text>;
  }
  if (kind === 'small') {
    return <Text className={focused ? 'font-inter text-[12px] text-[#3a3a42]' : 'font-inter text-[12px] text-muted'}
      numberOfLines={2}>{children}</Text>;
  }
  return <Text className={focused ? 'font-inter text-[13px] text-[#3a3a42]' : 'font-inter text-[13px] text-muted'}
    numberOfLines={2}>{children}</Text>;
}

function FocusIcon({name}) {
  const focused = useIsFocused();
  return <Icon name={name} dark={focused} />;
}

export function Dot({tone}) {
  return <View className="w-[8px] h-[8px] rounded-full" style={{backgroundColor: TONE_COLOR[tone] || TONE_COLOR.muted}} />;
}

export function TopBar({version, trail, freeText, onHistory, onAbout, onPower}) {
  return (
    <View className="flex-row items-center h-[64px] px-[48px] mt-[16px] gap-4">
      <Image source={logo} className="w-[38px] h-[38px] rounded-[10px]" />
      <Text className="font-semi text-[20px] text-snow">LZ4 Compression</Text>
      {version ? <Text className="font-inter text-[12px] text-muted mt-[4px]">{version}</Text> : null}
      {trail ? <Text className="font-inter text-[15px] text-muted ml-4" numberOfLines={1}>{trail}</Text> : null}
      <View className="flex-1" />
      {freeText ? <Text className="font-inter text-[13px] text-soft mr-2">{freeText}</Text> : null}
      {onHistory ? <RoundButton icon="history" onPress={onHistory} focusKey="top-history" /> : null}
      {onAbout ? <RoundButton icon="info" onPress={onAbout} focusKey="top-about" /> : null}
      {onPower ? <RoundButton icon="power" onPress={onPower} focusKey="top-power" /> : null}
    </View>
  );
}

export function RoundButton({icon, onPress, focusKey}) {
  return (
    <View onPress={onPress} focusKey={focusKey}
      className="w-[40px] h-[40px] rounded-full items-center justify-center bg-raised border border-line
        transition focused:bg-snow focused:border-snow focused:scale-110">
      <FocusIcon name={icon} />
    </View>
  );
}

// Big pill button (main actions, Start).
export function PrimaryButton({label, onPress, autoFocus, focusKey, danger}) {
  if (danger) {
    return (
      <View onPress={onPress} autoFocus={autoFocus} focusKey={focusKey}
        className="h-[52px] min-w-[240px] px-8 rounded-full items-center justify-center bg-[#3a1018] border-2
          border-bad transition focused:bg-bad focused:scale-105">
        <Text className="font-heavy text-[16px] text-snow">{label}</Text>
      </View>
    );
  }
  return (
    <View onPress={onPress} autoFocus={autoFocus} focusKey={focusKey}
      className="h-[52px] min-w-[240px] px-8 rounded-full items-center justify-center bg-raised border-2
        border-line transition focused:bg-snow focused:border-snow focused:scale-105">
      <FocusText kind="button">{label}</FocusText>
    </View>
  );
}

// One option card on a game page.
export const OptionCard = memo(function OptionCard({id, title, desc, icon, danger, onOpen, autoFocus}) {
  const open = () => onOpen(id);
  if (danger) {
    return (
      <View onPress={open} autoFocus={autoFocus} focusKey={'opt-' + id}
        className="flex-row items-center gap-4 w-[280px] h-[78px] px-4 rounded-[16px] bg-panel border border-line
          transition focused:bg-[#2a0d13] focused:border-bad focused:scale-[1.03]">
        <View className="w-[40px] h-[40px] rounded-[12px] items-center justify-center bg-[#3a1018]">
          <Icon name={icon} />
        </View>
        <View className="flex-1 gap-[2px]">
          <Text className="font-semi text-[15px] text-[#ff8a99]" numberOfLines={1}>{title}</Text>
          <Text className="font-inter text-[12px] text-muted" numberOfLines={2}>{desc}</Text>
        </View>
      </View>
    );
  }
  return (
    <View onPress={open} autoFocus={autoFocus} focusKey={'opt-' + id}
      className="flex-row items-center gap-4 w-[280px] h-[78px] px-4 rounded-[16px] bg-panel border border-line
        transition focused:bg-snow focused:border-snow focused:scale-[1.03]">
      <OptionIconBox icon={icon} />
      <View className="flex-1 gap-[2px]">
        <FocusText kind="title">{title}</FocusText>
        <FocusText kind="small">{desc}</FocusText>
      </View>
    </View>
  );
});

function OptionIconBox({icon}) {
  const focused = useIsFocused();
  return (
    <View className={focused ? 'w-[40px] h-[40px] rounded-[12px] items-center justify-center bg-ink'
      : 'w-[40px] h-[40px] rounded-[12px] items-center justify-center bg-raised'}>
      <Icon name={icon} />
    </View>
  );
}

// A selectable choice on an action page.
export function Choice({title, desc, selected, disabled, onPress, autoFocus, wide}) {
  if (disabled) {
    return (
      <View className={wide ? 'w-[420px] min-h-[74px] px-5 py-3 rounded-[16px] bg-panel border border-line opacity-40 justify-center'
        : 'w-[280px] min-h-[74px] px-5 py-3 rounded-[16px] bg-panel border border-line opacity-40 justify-center'}>
        <Text className="font-semi text-[15px] text-snow">{title}</Text>
        {desc ? <Text className="font-inter text-[12px] text-muted mt-[2px]" numberOfLines={2}>{desc}</Text> : null}
      </View>
    );
  }
  const body = (
    <>
      <View className="flex-1">
        <Text className="font-semi text-[15px] text-snow">{title}</Text>
        {desc ? <Text className="font-inter text-[12px] text-muted mt-[2px]" numberOfLines={2}>{desc}</Text> : null}
      </View>
      {selected ? (
        <View className="w-[24px] h-[24px] rounded-full bg-accent items-center justify-center ml-3">
          <Icon name="check" size="sm" />
        </View>
      ) : <View className="w-[24px] h-[24px] rounded-full border-2 border-line ml-3" />}
    </>
  );
  if (wide) {
    return (
      <View onPress={onPress} autoFocus={autoFocus} selected={selected}
        className="flex-row items-center w-[420px] min-h-[74px] px-5 py-3 rounded-[16px] bg-panel border-2
          border-line transition selected:border-accent focused:border-snow focused:scale-[1.03]">
        {body}
      </View>
    );
  }
  return (
    <View onPress={onPress} autoFocus={autoFocus} selected={selected}
      className="flex-row items-center w-[280px] min-h-[74px] px-5 py-3 rounded-[16px] bg-panel border-2
        border-line transition selected:border-accent focused:border-snow focused:scale-[1.03]">
      {body}
    </View>
  );
}

export function SectionLabel({children}) {
  return <Text className="font-semi text-[11px] text-muted tracking-[2px] mt-6 mb-3">{String(children).toUpperCase()}</Text>;
}

export function ProgressBar({percent}) {
  if (percent === null || percent === undefined) {
    return (
      <View className="h-[6px] rounded-full bg-line overflow-hidden">
        <View className="w-[30%] h-[6px] rounded-full bg-accent animate-pulse" />
      </View>
    );
  }
  return (
    <View className="h-[6px] rounded-full bg-line overflow-hidden">
      <View className="h-[6px] rounded-full bg-accent" style={{width: `${Math.max(1, percent)}%`}} />
    </View>
  );
}

// Label/value cells for a game's details (no pills).
export function Spec({label, value, tone}) {
  return (
    <View className="min-w-[132px] pr-6 py-2 border-l-2 border-line pl-4 gap-[3px]">
      <Text className="font-semi text-[10px] text-muted tracking-[1.6px]">{String(label).toUpperCase()}</Text>
      <View className="flex-row items-center gap-2">
        {tone ? <Dot tone={tone} /> : null}
        <Text className="font-semi text-[16px] text-snow" numberOfLines={1}>{value}</Text>
      </View>
    </View>
  );
}

export function Hint({children}) {
  return <Text className="font-inter text-[12px] text-muted">{children}</Text>;
}
