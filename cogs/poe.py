import asyncio
import re
import random
import poe.utils as utils

from discord import File, Embed
from io import BytesIO
from poe import Client
from PIL import Image
from discord.ext import commands
from utils.poe_search import find_one, cache_pob_xml
from utils import pastebin
from utils.poeurl import shrink_tree_url
from utils.responsive_embed import responsive_embed


class PathOfExile:
    def __init__(self, bot):
        self.bot = bot
        self.client = Client()
        self.re = re.compile(r'\[\[[^\]]+\]\]')

    @commands.command()
    async def link(self, ctx):
        item_matches = self.re.findall(ctx.message.content)
        if not item_matches:
            return
        tasks = []
        for item in item_matches:
            tasks.append(self.bot.loop.run_in_executor(None,
                                                       find_one, item.strip('[[').strip(']]'),
                                                       self.client, self.bot.loop))
        results = await asyncio.gather(*tasks)
        results = [x for x in results if x]
        images = []
        for result in results:
            if result.base == "Prophecy":
                flavor = 'prophecy'
            elif 'gem' in result.tags:
                flavor = 'gem'
            else:
                flavor = result.rarity
            r = utils.ItemRender(flavor)
            images.append(r.render(result))
        if len(images) > 1:
            box = [0, 0]
            for image in images:
                box[0] = box[0] + image.size[0]
                if image.size[1] > box[1]:
                    box[1] = image.size[1]
            box[0] = box[0] + (2*len(images))
            img = Image.new('RGBA', box, color='black')
            #img.show()
            paste_coords = [0, 0]
            for image in images:
                #image.show()
                img.paste(image.convert('RGBA'), box=paste_coords[:])
                paste_coords[0] = paste_coords[0] + image.size[0] + 2
        else:
            img = images[0]
        image_fp = BytesIO()
        img.save(image_fp, 'png')
        image_fp.seek(0)
        print("Image ready")
        await ctx.channel.send(file=File(image_fp, filename='image.png'))

    def _twoslot_pob(self, equip, itemtype):
        embed = Embed(color=0xb04040)
        if f'{itemtype} 1' in equip or f'{itemtype} 2' in equip:
            if f'{itemtype} 1' in equip and f'{itemtype} 2' in equip:
                rwp1 = utils.ItemRender(equip[f'{itemtype} 1']['object'].rarity)
                wp1 = rwp1.render(equip[f'{itemtype} 1']['object'])
                rwp2 = utils.ItemRender(equip[f'{itemtype} 2']['object'].rarity)
                wp2 = rwp2.render(equip[f'{itemtype} 2']['object'])
                box = list(wp1.size)
                if wp2.size[1] > box[1]:
                    box[1] = wp2.size[1]
                box[0] = box[0] + wp2.size[0] + 2
                img = Image.new('RGBA', box, color='black')
                img.paste(wp1.convert('RGBA'), box=(0, 0))
                img.paste(wp2.convert('RGBA'), box=(wp1.size[0]+2, 0))
            else:
                wp_n = f'{itemtype} 1' if f'{itemtype} 1' in equip else f'{itemtype} 2'
                rwp = utils.ItemRender(equip[wp_n]['object'].rarity)
                img = rwp.render(equip[wp_n]['object'])
            image_fp = BytesIO()
            img.save(image_fp, 'png')
            img.show()
            image_fp.seek(0)
            file = File(image_fp, filename=f'{itemtype.lower()}.png')
            embed.set_image(url=f"attachments://{file.filename}")

            slot_list = []
            if f'{itemtype} 1' in equip and 'gems' in equip[f'{itemtype} 1']:
                slot_list.append(f'{itemtype} 1')
            if f'{itemtype} 2' in equip and 'gems' in equip[f'{itemtype} 2']:
                slot_list.append(f'{itemtype} 2')
            for slot in slot_list:
                val_list = []
                for gem in equip[slot]['gems']:
                    val_list.append(f" - {gem['level']}/{gem['quality']} {gem['name']}")
                value = '\n'.join(val_list)
                embed.add_field(name=f"{slot} Gems", value=value, inline=True)
            return {'file': file, 'embed': embed}
        else:
            return None

    def _oneslot_pob(self, equip, itemtype):
        embed = Embed(color=0xb04040)
        if itemtype in equip:
            wp_n = itemtype
            rwp = utils.ItemRender(equip[wp_n]['object'].rarity)
            img = rwp.render(equip[wp_n]['object'])
            image_fp = BytesIO()
            img.save(image_fp, 'png')
            img.show()
            image_fp.seek(0)
            file = File(image_fp, filename=f"{itemtype.lower().replace(' ','')}.png")
            embed.set_image(url=f"attachments://{file.filename}")

            if 'gems' in equip[wp_n]:
                val_list = []
                for gem in equip[wp_n]['gems']:
                    val_list.append(f" - {gem['level']}/{gem['quality']} {gem['name']}")
                value = '\n'.join(val_list)
                embed.add_field(name=f"{wp_n} Gems", value=value, inline=True)
            return {'file': file, 'embed': embed}
        else:
            return None

    def _jewels_pob(self, equip):
        embed = Embed(color=0xb04040)
        if 'jewels' in equip:
            for jewel in equip['jewels']:
                name = jewel['base'] if jewel['rarity'].lower() != 'unique' else f"{jewel['name']} {jewel['base']}"
                val_list = [f" - {stat}" for stat in jewel['stats']]
                value = '\n'.join(val_list)
                embed.add_field(name=name, value=value, inline=True)
            return embed
        else:
            return None

    def _gem_groups(self, equip):
        embed = Embed(color=0xb04040)
        if 'gem_groups' in equip:
            for gem_title in equip['gem_groups']:
                name = gem_title
                val_list = []
                for gem in equip['gem_groups'][gem_title]:
                    val_list.append(f" - {gem['level']}/{gem['quality']} {gem['name']}")
                value = '\n'.join(val_list)
                embed.add_field(name=name, value=value, inline=True)
            return embed
        else:
            return None

    @commands.command()
    async def pob(self, ctx):
        paste_keys = pastebin.fetch_paste_key(ctx.message.content)
        if not paste_keys: return
        xml = None
        paste_key = random.choice(paste_keys)
        try:
            xml = await self.bot.loop.run_in_executor(None, pastebin.get_as_xml, paste_key)
        except:
            return
        if not xml: return
        stats = await self.bot.loop.run_in_executor(None, cache_pob_xml, xml, self.client)
        embed_dict = {}
        info = Embed(color=0xb04040)
        if stats['ascendancy'] != "None":
            info.title = f"Level {stats['level']} {stats['class']}: {stats['ascendancy']}"
        else:
            info.title = f"Level {stats['level']} stats['class']"

        info.description = \
        f"**Attributes:** Str: {stats['str']} **|** "\
        f"Dex: {stats['dex']} **|** "\
        f"Int: {stats['int']}\n"\
        f"**Charges:** Power: {stats['power_charges']} **|** " \
        f"Frenzy: {stats['frenzy_charges']} **|** " \
        f"Endurance: {stats['endurance_charges']}"

        offensive_stats_text =\
        f"**Total DPS:** {stats['total_dps']}\n"\
        f"**Crit Chance:** {stats['crit_chance']}\n"\
        f"**Effective Crit Chance:** {stats['crit_chance']}\n"\
        f"**Chance to Hit:** {stats['chance_to_hit']}%"

        defensive_stats_text =\
        f"**Life:** {stats['life']}\n"\
        f"**Life Regen:** {stats['life_regen']}\n"\
        f"**Energy Shield:** {stats['es']}\n"\
        f"**ES Regen:** {stats['es_regen']}\n"\
        f"**Degen:** {stats['degen']}"\

        mitigation_stats_text=\
        f"**Evasion:** {stats['evasion']}\n"\
        f"**Block:** {stats['block']}%\n"\
        f"**Spell Block:** {stats['spell_block']}%\n"\
        f"**Dodge:** {stats['dodge']}%\n"\
        f"**Spell Dodge:** {stats['spell_dodge']}%"

        resistances_text = \
        f"**Fire:** {stats['fire_res']}%\n"\
        f"**Cold:** {stats['cold_res']}%\n" \
        f"**Lightning:** {stats['light_res']}%\n" \
        f"**Chaos:** {stats['chaos_res']}%"

        skill_trees = ""
        for tree in stats['trees']:
            #skill_trees += f"[{tree}]({shrink_tree_url(stats['trees'][tree])})\n"
            skill_trees += f"[{tree}]\n"

        info.add_field(name="Offense", value=offensive_stats_text)
        info.add_field(name="Defense", value=defensive_stats_text, inline=True)
        info.add_field(name="Mitigation", value=mitigation_stats_text, inline=True)
        info.add_field(name="Resistances", value=resistances_text, inline=True)
        info.add_field(name="Skill Trees", value=skill_trees, inline=False)
        info.set_thumbnail(url="https://images-ext-2.discordapp.net/external/lZwHlcJYEP_-CeL744a7RSWVnhrIifPJgiIcmKkDuJY/https/pastebin.com/i/facebook.png")

        responsive_dict = {}
        files = []
        weapons_dict = self._twoslot_pob(stats['equipped'], 'Weapon')
        rings_dict = self._twoslot_pob(stats['equipped'], 'Ring')
        amulet_dict = self._oneslot_pob(stats['equipped'], 'Amulet')
        armor_dict = self._oneslot_pob(stats['equipped'], 'Body Armour')
        gloves_dict = self._oneslot_pob(stats['equipped'], 'Gloves')
        boots_dict = self._oneslot_pob(stats['equipped'], 'Boots')
        belt_dict = self._oneslot_pob(stats['equipped'], 'Belt')
        jewels_dict = self._jewels_pob(stats)
        gem_groups_dict = self._gem_groups(stats['equipped'])
        responsive_dict['info'] = info
        if weapons_dict:
            responsive_dict['weapons'] = weapons_dict['embed']
            files.append(weapons_dict['file'])
        if rings_dict:
            responsive_dict['rings'] = rings_dict['embed']
            files.append(rings_dict['file'])
        if amulet_dict:
            responsive_dict['amulet'] = amulet_dict['embed']
            files.append(weapons_dict['file'])
        if armor_dict:
            responsive_dict['armor'] = armor_dict['embed']
            files.append(armor_dict['file'])
        if gloves_dict:
            responsive_dict['gloves'] = gloves_dict['embed']
            files.append(gloves_dict['file'])
        if boots_dict:
            responsive_dict['boots'] = boots_dict['embed']
            files.append(boots_dict['file'])
        # if belt_dict:
        #     responsive_dict['belt'] = belt_dict['embed']
        #     files.append(boots_dict['file'])
        if jewels_dict:
            responsive_dict['jewels'] = jewels_dict
        if gem_groups_dict:
            responsive_dict['gems'] = gem_groups_dict
        await responsive_embed(self.bot, responsive_dict, ctx, files)

def setup(bot):
    bot.add_cog(PathOfExile(bot))