import React from 'react';
import {CoverColorPicker} from './cover_color_picker.jsx';
export {COMMON_COLORS,CommonColorPalette} from './common_color_swatches.jsx';

export function CommonColorOptions(props) {
  const current=typeof props.value==='string'&&/^#[0-9a-f]{6}$/i.test(props.value)
    ?props.value:'#5672CA';
  return <details className="madar-common-colors__details">
    <summary aria-label={'انتخاب رنگ '+(props.label||'')}>
      <span className="madar-common-colors__preview" style={{backgroundColor:current}} aria-hidden="true"/>
      <span>رنگ</span>
    </summary>
    <CoverColorPicker {...props}/>
  </details>;
}
