import xml.etree.ElementTree as ET
import subprocess
import os
import re

def parse_params(inner):
    """Parses MediaWiki template parameters into a dict and a list of positional params."""
    parts = []
    current = ""
    depth = 0
    for char in inner:
        if char in '{[': depth += 1
        elif char in '}]': depth -= 1
        if char == '|' and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    name = parts[0].strip()
    params = {}
    positional = []
    for i, p in enumerate(parts[1:]):
        if '=' in p and '[[' not in p.split('=', 1)[0]:
            k, v = p.split('=', 1)
            params[k.strip()] = v.strip()
        else:
            val = p.strip()
            positional.append(val)
            params[str(i+1)] = val
    return name, params, positional

def preprocess_mediawiki(content):
    # Strip HTML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    # Strip problematic attributes from table cells while preserving pipes
    def clean_attrs(match):
        marker = match.group(1); attrs = match.group(2)
        for attr in ['data-sort-value', 'style', 'width', 'align', 'valign', 'colspan', 'rowspan']:
            attrs = re.sub(f'{attr}="[^"]*"', '', attrs)
        attrs = attrs.strip()
        return marker if not attrs else f"{marker} {attrs} |"

    content = re.sub(r'^([ \t]*[|!][^-])([^|\n]+)\|', clean_attrs, content, flags=re.MULTILINE)
    content = re.sub(r'([|!][|!])([^|\n]+)\|', clean_attrs, content)

    # Basic replacements
    content = content.replace("{{MC}}", "Minecraft").replace("{{mc}}", "Minecraft")
    
    # Bug template - handle early
    content = re.sub(r'\{\{bug\|([^|}]*).*?\}\}', r'[\1](https://bugs.mojang.com/browse/\1)', content, flags=re.IGNORECASE)
    
    # Simple inline templates
    content = re.sub(r'\{\{(control|key|Slot|S|SimpleGrid|Grid/[^|}]+)\|([^|}]+).*?\}\}', r'\2', content)
    content = re.sub(r'\{\{color\|.*?\|(.*?)\}\}', r'\1', content, flags=re.IGNORECASE)
    
    # Simple links
    content = re.sub(r'\{\{(ItemLink|BlockLink|EntityLink|EnvLink|L|Link)\|([^|}]+).*?\}\}', r'[[\2]]', content)
    
    # History tables
    content = content.replace("{{HistoryTable}}", "\n### History\n").replace("{{HistoryTable|end=1}}", "")
    content = re.sub(r'\{\{HistoryLine\|([^|]+)\|([^}]+)\}\}', r'- \1: \2', content)

    iteration = 0
    while iteration < 5:
        innermost_templates = list(re.finditer(r'\{\{([^{}]+)\}\}', content, flags=re.DOTALL))
        if not innermost_templates: break
        changed = False
        for match in reversed(innermost_templates):
            full_text = match.group(0); inner = match.group(1); start, end = match.span()
            name, params, positional = parse_params(inner); name_low = name.lower().strip()
            res = None
            if name_low == 'crafting':
                output = params.get('Output', 'Unknown')
                ingredients = [f"{k}: {v}" for k, v in params.items() if k.isdigit() or (k not in ['Output', 'ignoreusage', 'shapeless', 'fixed', 'notable'])]
                res = f"\n**Crafting Recipe for {output}**\n"
                for ing in ingredients: res += f"- {ing}\n"
                res += f"**Output**: {output}\n"
            elif name_low in ['info', 'note', 'important', 'warning', 'tip']:
                res = f"\n> **{name.upper()}**: {params.get('1', '')}\n"
            elif name_low == 'msgbox':
                res = f"\n> ### {params.get('title', '')}\n> {params.get('text', params.get('1', ''))}\n"
            elif name_low in ['for', 'about', 'distinguish', 'stub', 'reflist', 'notelist', 'navbox', 'hatnote', 'exclusive', 'short description', 'redirect', 'relevant tutorial', 'anchor', 'see also', 'main', 'verify', 'more images', 'conjecture', 'in']:
                res = ""
            elif name_low in ['advancementrow', 'achievementrow']:
                res = f"\n#### {params.get('title', params.get('1', 'Unknown'))}\n- **Description**: {params.get('4', params.get('2', ''))}\n- **Requirement**: {params.get('6', params.get('3', ''))}\n"
            elif name_low == 'enchantlevelstablerow':
                res = "\n|-\n| " + " || ".join(positional) + "\n"
            elif name_low == 'flatlist':
                res = "\n" + "\n".join(positional) + "\n"
            elif name_low == 'tabber':
                res = "\n"
                for i in range(1, 10):
                    nk = f'tabname{i}'; ck = f'tabcontent{i}'
                    if nk in params: res += f"#### {params[nk]}\n{params.get(ck, '')}\n"
                if res == "\n": res = "\n" + "\n".join(positional) + "\n"
            else:
                res = positional[0] if positional else ""
            if res is not None:
                content = content[:start] + res + content[end:]
                changed = True
        if not changed: break
        iteration += 1
    return content

def postprocess_markdown(content):
    # Fix wikilinks: [Text](Target "Title"){.wikilink} -> [Text](SanitizedTarget.md)
    pattern1 = r'\[(?P<text>[^\]]+?)\]\((?P<target>[^\)]+?)(?:\s+"(?P<title>[^"]*?)")?\)\{\.wikilink\}'
    def replace_link1(match):
        text = match.group('text'); target = match.group('target')
        if target.startswith('http'): return f"[{text}]({target})"
        if target.lower().startswith(('file:', 'image:', ':file:', ':image:')):
            s = re.sub(r'[\\/*?:"<>|]', "", target.split(':')[-1]).replace(" ", "_")
            return f"[{text}]({s})"
        base_t = target.split('#')[0]; anchor = ('#' + target.split('#')[1]) if '#' in target else ''
        s = re.sub(r'[\\/*?:"<>|]', "", base_t).replace(" ", "_")
        return f"[{text}]({s}.md{anchor})"
    content = re.sub(pattern1, replace_link1, content)

    # Handle HTML links
    pattern2 = r'<a href="(?P<target>[^"]+?)" class="wikilink" title="(?P<title>[^"]*?)">(?P<text>.*?)</a>'
    def replace_link2(match):
        text = match.group('text'); target = match.group('target')
        if target.startswith('http'): return f"[{text}]({target})"
        base_t = target.split('#')[0]; anchor = ('#' + target.split('#')[1]) if '#' in target else ''
        s = re.sub(r'[\\/*?:"<>|]', "", base_t).replace(" ", "_")
        return f"[{text}]({s}.md{anchor})"
    content = re.sub(pattern2, replace_link2, content)

    # Fix escaped quotes
    content = content.replace(r"\'", "'").replace(r'\"', '"')
    
    # Remove header hashlinks (e.g., {#differences_from_singleplayer})
    content = re.sub(r'^(#+ .*?) \{#.*?\}$', r'\1', content, flags=re.MULTILINE)
    
    # Fix escaped bugtracker links \[MC-123\](...) -> [MC-123](...)
    content = content.replace(r'\[MC-', '[MC-').replace(r'\](https://bugs.mojang.com', '](https://bugs.mojang.com')

    content = re.sub(r'\.(png|jpg)\.md', r'.\1', content)
    return content

def convert_mediawiki_xml(xml_path, output_dir):
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    mw_dir = os.path.join(output_dir, "mw_pages")
    if not os.path.exists(mw_dir): os.makedirs(mw_dir)
    ns = {'mw': 'http://www.mediawiki.org/xml/export-0.11/'}
    try:
        print(f"Parsing {xml_path}...")
        tree = ET.parse(xml_path); root = tree.getroot(); pages = root.findall('.//mw:page', ns)
        print(f"Found {len(pages)} pages. Starting conversion...")
        for i, page in enumerate(pages):
            title = page.find('mw:title', ns).text
            if ':' in title and title.split(':')[0] in ['Template', 'Module', 'MediaWiki', 'Category'] and not title.startswith('Category:'): continue
            safe_title = re.sub(r'[\\/*?:"<>|]', "", title).replace(" ", "_")
            revision = page.find('mw:revision', ns); text_element = revision.find('mw:text', ns)
            if text_element is not None and text_element.text:
                mw_content = text_element.text
                processed_content = preprocess_mediawiki(mw_content)
                output_md = os.path.join(output_dir, f"{safe_title}.md")
                temp_mw = os.path.join(mw_dir, f"temp_{i}.mw")
                with open(temp_mw, 'w', encoding='utf-8') as f: f.write(processed_content)
                result = subprocess.run(['pandoc', '-f', 'mediawiki', '-t', 'markdown', '--wrap=none', temp_mw], capture_output=True, text=True, encoding='utf-8')
                if result.returncode == 0:
                    fixed_content = postprocess_markdown(result.stdout)
                    with open(output_md, 'w', encoding='utf-8') as f: f.write(fixed_content)
                else: print(f"Error converting {title}: {result.stderr}")
                os.remove(temp_mw)
                if (i+1) % 20 == 0 or i == len(pages)-1: print(f"[{i+1}/{len(pages)}] Converted: {title}")
        print(f"\nSuccess! All files saved to: {os.path.abspath(output_dir)}")
    except Exception as e: print(f"Error: {e}")

input_xml = os.path.expanduser("~/Downloads/Minecraft+Wiki-20260314190550.xml")
output_folder = "minecraft_markdown_pages"

if __name__ == "__main__":
    convert_mediawiki_xml(input_xml, output_folder)
