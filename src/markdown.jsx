import React from 'react';

// Only a small Markdown subset is rendered. React escapes all user text, and
// URLs are explicitly allowlisted; stored HTML is never interpreted as markup.
export function safeMarkdownUrl(value){
  const url=String(value||'').trim();
  if(!url||/[\u0000-\u0020\u007f]/.test(url))return null;
  try{
    const parsed=new URL(url);
    return ['https:','http:','mailto:'].includes(parsed.protocol)?url:null;
  }catch{return null;}
}

const INLINE=/(\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*([^*\n]+)\*\*|`([^`\n]+)`|\*([^*\n]+)\*)/g;
export function markdownInline(source){
  const text=String(source||'');
  const output=[];
  let last=0;
  for(const match of text.matchAll(INLINE)){
    if(match.index>last)output.push(text.slice(last,match.index));
    const key=match.index;
    if(match[2]!==undefined){
      const href=safeMarkdownUrl(match[3]);
      output.push(href?<a key={key} href={href} target="_blank" rel="noopener noreferrer">{match[2]}</a>:match[0]);
    }else if(match[4]!==undefined)output.push(<strong key={key}>{match[4]}</strong>);
    else if(match[5]!==undefined)output.push(<code key={key}>{match[5]}</code>);
    else output.push(<em key={key}>{match[6]}</em>);
    last=match.index+match[0].length;
  }
  if(last<text.length)output.push(text.slice(last));
  return output;
}

export function MarkdownPreview({value='',direction='auto'}){
  const lines=String(value||'').replace(/\r\n?/g,'\n').split('\n');
  const blocks=[];
  let i=0;
  while(i<lines.length){
    const line=lines[i];
    if(!line.trim()){i++;continue;}
    if(/^\s*```/.test(line)){
      const language=line.trim().slice(3).trim().slice(0,30);
      const code=[];i++;
      while(i<lines.length&&!/^\s*```\s*$/.test(lines[i]))code.push(lines[i++]);
      if(i<lines.length)i++;
      blocks.push(<pre key={blocks.length}><code data-language={language||undefined}>{code.join('\n')}</code></pre>);
      continue;
    }
    const heading=/^\s{0,3}(#{1,3})\s+(.+)$/.exec(line);
    if(heading){
      const Tag=`h${heading[1].length+2}`;
      blocks.push(<Tag key={blocks.length}>{markdownInline(heading[2])}</Tag>);i++;continue;
    }
    const list=/^\s{0,3}(?:([-*+])|(\d+)[.)])\s+(.+)$/.exec(line);
    if(list){
      const ordered=!!list[2],items=[];
      while(i<lines.length){
        const next=/^\s{0,3}(?:([-*+])|(\d+)[.)])\s+(.+)$/.exec(lines[i]);
        if(!next||!!next[2]!==ordered)break;
        items.push(<li key={i}>{markdownInline(next[3])}</li>);i++;
      }
      blocks.push(ordered?<ol key={blocks.length}>{items}</ol>:<ul key={blocks.length}>{items}</ul>);
      continue;
    }
    if(/^\s{0,3}>\s?/.test(line)){
      const quotes=[];
      while(i<lines.length&&/^\s{0,3}>\s?/.test(lines[i]))quotes.push(lines[i++].replace(/^\s{0,3}>\s?/,''));
      blocks.push(<blockquote key={blocks.length}>{quotes.map((q,j)=><React.Fragment key={j}>{j>0&&<br/>}{markdownInline(q)}</React.Fragment>)}</blockquote>);
      continue;
    }
    const paragraph=[];
    while(i<lines.length&&lines[i].trim()&&!/^\s*```/.test(lines[i])&&
      !/^\s{0,3}(?:#{1,3}\s+|[-*+]\s+|\d+[.)]\s+|>\s?)/.test(lines[i]))paragraph.push(lines[i++]);
    // A paragraph may begin with unrecognized Markdown syntax; consume it as text.
    if(!paragraph.length)paragraph.push(lines[i++]);
    blocks.push(<p key={blocks.length}>{paragraph.map((part,j)=><React.Fragment key={j}>{j>0&&<br/>}{markdownInline(part)}</React.Fragment>)}</p>);
  }
  return <div className="rich-preview" dir={direction}>{blocks.length?blocks:<p className="rich-empty">توضیحی ثبت نشده است.</p>}</div>;
}
