import asyncio
import discord
from discord.ext import commands, menus, tasks


intents = discord.Intents.all()
bot = commands.Bot(command_prefix='/', intents=intents)

teams = {}
players = {}
rostercap = 10
TEAM_CAPTAIN_ROLE = "Franchise Owner"

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print('------')

# Assuming you have these dictionaries defined somewhere
# players = {}
# teams = {}

class TradeMenu(menus.Menu):
    def __init__(self, ctx, group_number, players_list):
        super().__init__(timeout=60.0, delete_message_after=True)
        self.ctx = ctx
        self.group_number = group_number
        self.players_list = players_list
        self.selected_players = []

    async def send_initial_message(self, ctx, channel):
        return await ctx.send(f"Please mention the players for the {self.group_number} group: {', '.join([player.display_name for player in self.players_list])}")

    async def check_author(self, payload):
        return payload.user_id == self.ctx.author.id and payload.message_id == self.message.id

    async def reaction_task(self, payload):
        player = discord.utils.get(self.ctx.message.mentions, id=payload.user_id)
        if player:
            self.selected_players.append(player)
            await self.ctx.send(f"{player.display_name} added to the {self.group_number} group.")
        else:
            await self.ctx.send("Invalid mention. Please mention a player from the list.")

    async def finalize(self, timed_out):
        if not timed_out:
            await self.ctx.send(f"{', '.join([player.display_name for player in self.selected_players])} added to the {self.group_number} group.")

async def perform_trade(ctx, first_group, second_group):
    try:
        print(f"First Group: {first_group}")
        print(f"Second Group: {second_group}")

        # Print current state of teams and players
        print("Current state before trade:")
        print("Teams:", teams)
        print("Players:", players)

        # Get team names from the first player in each group
        first_team_name = players[first_group[0].id]['team']
        second_team_name = players[second_group[0].id]['team']

        # Perform the trade logic
        for player in first_group:
            # Remove player from their current team
            current_team = players[player.id]['team']
            teams[current_team]['players'].remove(player.id)

            # Assign player to the new team
            new_team = teams.get(second_team_name)
            if new_team is None:
                # If the new team doesn't exist, create it
                teams[second_team_name] = {'players': [], 'captain': None}
                new_team = teams[second_team_name]

            print(f"Assigning {player.display_name} to new team {second_team_name} ({new_team})")
            new_team['players'].append(player.id)
            players[player.id]['team'] = second_team_name

        for player in second_group:
            # Remove player from their current team
            current_team = players[player.id]['team']
            teams[current_team]['players'].remove(player.id)

            # Assign player to the new team
            new_team = teams.get(first_team_name)
            if new_team is None:
                # If the new team doesn't exist, create it
                teams[first_team_name] = {'players': [], 'captain': None}
                new_team = teams[first_team_name]

            print(f"Assigning {player.display_name} to new team {first_team_name} ({new_team})")
            new_team['players'].append(player.id)
            players[player.id]['team'] = first_team_name

        # Print updated state of teams and players
        print("Current state after trade:")
        print("Teams:", teams)
        print("Players:", players)

    except Exception as e:
        print(f"Error during trade: {e}")
        raise e  # Reraise the exception

async def remove_old_roles(member):
    # Remove old team roles from the member
    for team_name, team_data in teams.items():
        if member.id in team_data['players']:
            role = discord.utils.get(member.guild.roles, name=team_name)
            if role:
                await member.remove_roles(role)

def is_team_captain(ctx):
    author_id = ctx.author.id
    for team_name, team_data in teams.items():
        if team_data['captain'] == author_id:
            return True
    return False

@bot.command(name='teamlist', help='Display a list of teams and their total stars divided by the roster cap')
async def team_list(ctx):
    try:
        if not teams:
            await ctx.send("No teams found.")
            return

        team_list_embed = discord.Embed(title='Team List', color=discord.Color.blue())

        for team_name, team_data in teams.items():
            total_stars = sum(players.get(player, {}).get('stars', 0) for player in team_data['players'])
            roster_cap = team_data.get('rostercap', 10)  # Default to 10 if not set
            star_percentage = (total_stars / roster_cap) * 100
            team_list_embed.add_field(name=f'{team_name} (Total Stars: {total_stars}/{roster_cap})', value=f'{star_percentage:.2f}% of Roster Cap', inline=False)

        await ctx.send(embed=team_list_embed)

    except Exception as e:
        error_message = str(e)
        await ctx.send(f'Error during team list: {error_message}')

@bot.command(name='sign', description='Sign a player to your team')
@commands.has_role(TEAM_CAPTAIN_ROLE)
async def sign(ctx, player: discord.Member):
    try:
        # Check if the author belongs to a team
        if ctx.author.id not in players or not players[ctx.author.id]['team']:
            await ctx.send("You don't belong to a team. Create or join a team first.")
            return

        team_name = players[ctx.author.id]['team']

        # Check if the team exists
        if team_name not in teams:
            await ctx.send(f"Team {team_name} does not exist. Create the team first!")
            return

        # Check if the player is already in the team
        if player.id in teams[team_name]['players']:
            await ctx.send(f'{player.display_name} is already in {team_name}.')
            return

        # Send a direct message to the player asking for confirmation
        confirmation_message = await player.send(
            f'{ctx.author.display_name} is trying to sign you to their team ({team_name}). Do you accept? (yes/no)'
        )

        # Add reactions to the confirmation message
        await confirmation_message.add_reaction('✅')  # thumbs up
        await confirmation_message.add_reaction('❌')  # thumbs down

        def check(reaction, user):
            return user == player and reaction.message == confirmation_message and str(reaction.emoji) in ['✅', '❌']

        # Wait for the player's response
        reaction, _ = await bot.wait_for('reaction_add', check=check, timeout=86400)

        if str(reaction.emoji) == '✅':
            # Add the player to the team
            teams[team_name]['players'].append(player.id)
            players[player.id] = {'team': team_name, 'stars': 0}

            # Get the team role
            team_role = discord.utils.get(ctx.guild.roles, name=team_name)

            # Assign the team role to the player
            await player.add_roles(team_role)

            await ctx.send(f'{player.display_name} has been signed to {team_name}!')
        else:
            await ctx.send(f'{player.display_name} declined the signing.')

    except Exception as e:
        print(f"Error during signing: {e}")
        await ctx.send("An error occurred during the signing.")



@bot.command(name='player', description='Display player information')
async def player_info(ctx, player_mention: discord.Member):
    try:
        # Check if the player exists in the players dictionary
        if player_mention.id in players:
            player_name = player_mention.display_name
            team_name = players[player_mention.id]['team']
            stars = players[player_mention.id]['stars']

            # Create an embed
            embed = discord.Embed(
                title=f'Player Information: {player_name}',
                description=f'Team: {team_name}\nStars: {stars}',
                color=discord.Color.blue()
            )

            # Set thumbnail as player's avatar if available
            embed.set_thumbnail(url=player_mention.avatar.url)

            await ctx.send(embed=embed)
        else:
            await ctx.send(f'Player {player_mention.display_name} not found.')

    except Exception as e:
        error_message = str(e)
        await ctx.send(f'Error: {error_message}')


@bot.command(name='trade')
@commands.check(lambda ctx: is_team_captain(ctx))
async def trade(ctx):
    try:
        await ctx.send("Please mention the players for the first group:")

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel

        # Wait for the user to mention the players for the first group
        first_group_message = await bot.wait_for('message', check=check, timeout=60)

        first_group = first_group_message.mentions

        # Check if the author is the captain of the team to which the first group of players belongs
        author_is_captain = is_team_captain(ctx)
        if not author_is_captain:
            await ctx.send("You must be the captain of the team to trade those players.")
            return

        await ctx.send("Please mention the players for the second group:")

        # Wait for the user to mention the players for the second group
        second_group_message = await bot.wait_for('message', check=check, timeout=60)

        second_group = second_group_message.mentions

        # Print the first and second groups
        print(f"First Group: {first_group}")
        print(f"Second Group: {second_group}")

        # Send a confirmation message to the team captain (Franchise Owner) of the team of players in group2
        team_of_group2 = players.get(second_group[0].id, {}).get('team')
        if team_of_group2:
            captain_id = teams[team_of_group2].get('captain')
            captain = ctx.guild.get_member(captain_id)
            if captain:
                # Send a direct message to the team captain (Franchise Owner) for confirmation
                trade_message = f"Trade Proposal:\n\nGroup 1: {', '.join([player.display_name for player in first_group])}\nGroup 2: {', '.join([player.display_name for player in second_group])}\n\nPlease confirm the trade by reacting with 👍 or reject with 👎."
                confirmation_message = await captain.send(trade_message)

                # Add reactions to the confirmation message
                await confirmation_message.add_reaction('👍')  # thumbs up
                await confirmation_message.add_reaction('👎')  # thumbs down

                def check_reactions(reaction, user):
                    return user == captain and reaction.message == confirmation_message and str(reaction.emoji) in ['👍', '👎']

                # Wait for the captain's response
                reaction, _ = await bot.wait_for('reaction_add', check=check_reactions, timeout=86400)

                if str(reaction.emoji) == '👎':
                    await ctx.send("Trade canceled. The team captain (Franchise Owner) did not confirm.")
                    return
                elif str(reaction.emoji) == '👍':
                    # Start the voting logic for approval
                    trade_confirmation = await ctx.send("Vote to approve or reject the trade. React with 👍 to approve, 👎 to reject.")
                    await trade_confirmation.add_reaction('👍')
                    await trade_confirmation.add_reaction('👎')

                    # Wait for reactions for a specific duration (20 seconds)
                    await asyncio.sleep(20)

                    # Get updated message
                    trade_confirmation = await ctx.channel.fetch_message(trade_confirmation.id)

                    # Fetch the reactions
                    thumbs_up = 0
                    thumbs_down = 0
                    for reaction in trade_confirmation.reactions:
                        if str(reaction.emoji) == '👍':
                            thumbs_up += reaction.count - 1  # Subtract 1 to exclude the bot's own reaction
                        elif str(reaction.emoji) == '👎':
                            thumbs_down += reaction.count - 1  # Subtract 1 to exclude the bot's own reaction

                    if thumbs_up > thumbs_down:
                        # Trade approved, proceed with the trade logic
                        await perform_trade(ctx, first_group, second_group)
                        await ctx.send("Trade completed.")
                    else:
                        await ctx.send("Trade rejected. Not enough approval votes.")

        else:
            await ctx.send("Could not determine the team of players in the second group.")

    except asyncio.TimeoutError:
        await ctx.send("Trade timed out. Please run the command again.")

    except Exception as e:
        print(f"Error during trade: {e}")
        await ctx.send("An error occurred during the trade.")





async def notify_team_captain(guild, team_name, first_group, second_group):
    # Get the team captain (franchise owner) role
    captain_role = discord.utils.get(guild.roles, name="franchise owner")  # Adjust the role name as needed

    if captain_role:
        # Get the team captain (franchise owner) for the specified team
        team_captains = [member for member in guild.members if captain_role in member.roles and is_team_captain(member, team_name)]

        # Notify each team captain
        for captain in team_captains:
            try:
                # Send a direct message to the team captain with trade details
                trade_message = f"Trade Proposal:\n\nGroup 1: {', '.join([player.display_name for player in first_group])}\nGroup 2: {', '.join([player.display_name for player in second_group])}\n\nPlease confirm the trade by reacting with 👍 or reject with 👎."
                await captain.send(trade_message)

            except discord.Forbidden:
                print(f"Unable to send a direct message to {captain.display_name} (ID: {captain.id}).")


async def update_roles(guild, player_id):
    member = guild.get_member(player_id)
    if member:
        # Check if the player is associated with any team
        if player_id in players:
            current_team_name = players[player_id]['team']
            
            # Remove old team role
            if current_team_name:
                old_role = discord.utils.get(guild.roles, name=current_team_name)
                if old_role:
                    await member.remove_roles(old_role)

            # Add new team role
            new_team_name = teams[current_team_name]['players']
            if new_team_name:
                new_role = discord.utils.get(guild.roles, name=new_team_name)
                if new_role:
                    await member.add_roles(new_role)

# Define your update_roles task
@tasks.loop(seconds=60)  # Update every 60 seconds, adjust as needed
async def update_roles_task():
    for guild in bot.guilds:
        for player_id in players.keys():
            await update_roles(guild, player_id)

# Start the task when the bot is ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    update_roles_task.start()

        
@bot.command(name='setcaptain', help='Set a team captain')
@commands.has_permissions(administrator=True)
async def set_captain(ctx, team_name: str, captain: discord.Member):
    try:
        # Check if the team exists
        if team_name not in teams:
            await ctx.send(f'Team {team_name} does not exist.')
            return

        # Check if the captain is in the team
        if captain.id not in teams[team_name]['players']:
            await ctx.send(f'{captain.display_name} is not in {team_name}.')
            return

        # Set the captain for the team
        teams[team_name]['captain'] = captain.id

        await ctx.send(f'{captain.display_name} is now the captain of {team_name}.')

    except Exception as e:
        error_message = str(e)
        await ctx.send(f'Error: {error_message}')

@bot.command(name='createteam', description='Create a team and role')
@commands.has_permissions(administrator=True)
async def create_team(ctx, team_name: str):
    try:
        if team_name not in teams:
            teams[team_name] = {'players': [], 'captain': None}

            # Create the team role
            team_role = await ctx.guild.create_role(name=team_name)

            # Move the team role below the bot's role
            await team_role.edit(position=ctx.guild.me.top_role.position - 1)

            # Assign the role to the person who created the team (optional)
            await ctx.author.add_roles(team_role)

            await ctx.send(f'Team {team_name} created!')

        else:
            await ctx.send(f'Team {team_name} already exists. Choose a different name.')

    except Exception as e:
        error_message = str(e)
        await ctx.send(f'Error: {error_message}')

@bot.command(name='addplayer')
@commands.has_permissions(administrator=True)
async def add_player(ctx, member: discord.Member, team_name):
    try:
        player_name = member.name  # Use member.name as the player_name
        player_id = member.id  # Use member.id as the player_id

        # Check if the team exists
        if team_name not in teams:
            await ctx.send(f'Team {team_name} does not exist. Create the team first!')
            return

        # Check if the player is already in the team
        if player_id in teams[team_name]['players']:
            await ctx.send(f'{member.display_name} is already in {team_name}')
            return

        # Check if adding the player would exceed the roster star cap
        current_roster_stars = sum(players[player]['stars'] for player in teams[team_name]['players'])
        new_player_stars = players.get(player_id, {'stars': 0})['stars']
        if current_roster_stars + new_player_stars > rostercap:
            await ctx.send(f'Adding {member.display_name} to {team_name} would exceed the roster star cap!')
            return

        # Add the player to the team
        teams[team_name]['players'].append(player_id)
        players[player_id] = {'team': team_name, 'stars': 0}

        await ctx.send(f'{member.display_name} added to {team_name}')

    except Exception as e:
        error_message = str(e)
        await ctx.send(f'Error: {error_message}')

@bot.command(name='roster')
async def display_roster(ctx, team_name):
    try:
        # Check if the team exists
        if team_name not in teams:
            await ctx.send(f'Team {team_name} does not exist.')
            return

        # Check if the team has players
        if not teams[team_name]['players']:
            await ctx.send(f'Team {team_name} has no players.')
            return

        # Create an embed for the roster
        roster_embed = discord.Embed(title=f'**{team_name} Roster**', color=discord.Color.blue())

        # Iterate over players in the team and add them to the embed
        for player_id in teams[team_name]['players']:
            # Get player information
            player_name = ctx.guild.get_member(player_id).display_name
            stars = players.get(player_id, {}).get('stars', 0)

            # Add player information to the embed
            roster_embed.add_field(name=f'**{player_name}**', value=f'Stars: {stars}', inline=False)

        # Calculate and add the sum of stars for the team divided by roster cap
        roster_cap = teams[team_name].get('rostercap', 10)  # Default to 10 if not set
        total_stars = sum(players.get(player, {}).get('stars', 0) for player in teams[team_name]['players'])
        roster_embed.add_field(name='**Star Cap**', value=f'{total_stars}/{roster_cap}', inline=False)

        await ctx.send(embed=roster_embed)

    except Exception as e:
        error_message = str(e)
        await ctx.send(f'Error: {error_message}')


@bot.command(name='editstars')
@commands.has_permissions(administrator=True)
async def edit_stars(ctx, member: discord.Member, stars):
    try:
        player_id = member.id  # Use member.id as the player_id

        # Check if the player is in the players dictionary
        if player_id in players:
            # Edit the stars for the player
            players[player_id]['stars'] = int(stars)

            # Get the team name of the player
            team_name = players[player_id]['team']

            # Check if the team exists and has a roster cap
            if team_name in teams and 'rostercap' in teams[team_name]:
                roster_cap = teams[team_name]['rostercap']

                # Calculate the total stars for the team
                total_stars = sum(players[p]['stars'] for p in teams[team_name]['players'])

                # Check if the team exceeds the roster cap
                if total_stars > roster_cap:
                    await ctx.send(f"Warning: Team {team_name} exceeds the roster cap of {roster_cap} stars. They cannot play anymore.")
                    return

            await ctx.send(f'Stars for {member.display_name} updated to {stars}.')
        else:
            await ctx.send(f'{member.display_name} is not a registered player.')

    except Exception as e:
        error_message = str(e)
        await ctx.send(f'Error: {error_message}')


@bot.command(name='rostercap', help='Set the maximum star cap for a team')
@commands.has_permissions(administrator=True)
async def set_roster_cap(ctx, team_name: str, cap: int):
    try:
        if team_name not in teams:
            raise ValueError(f'Team {team_name} does not exist.')

        # Update the roster cap for the team
        teams[team_name]['rostercap'] = cap

        await ctx.send(f'Roster cap for {team_name} set to {cap} stars.')

    except ValueError as e:
        error_message = str(e)
        await ctx.send(f'Error: {error_message}')


@bot.command(name='removeplayer')
@commands.has_permissions(administrator=True)
async def remove_player(ctx, member: discord.Member, team_name):
    try:
        player_id = member.id  # Use member.id as the player_id

        # Check if the team exists
        if team_name not in teams:
            await ctx.send(f'Team {team_name} does not exist.')
            return

        # Check if the player is in the team
        if player_id not in teams[team_name]['players']:
            await ctx.send(f'{member.display_name} is not in {team_name}.')
            return

        # Remove the player from the team
        teams[team_name]['players'].remove(player_id)
        players.pop(player_id, None)

        await ctx.send(f'{member.display_name} removed from {team_name}')

    except Exception as e:
        error_message = str(e)
        await ctx.send(f'Error: {error_message}')


@bot.command(name='updateplayers')
@commands.has_permissions(administrator=True)
async def update_players(ctx):
    try:
        # Iterate through all members in the server
        for member in ctx.guild.members:
            player_id = member.id  # Use member.id as the player_id

            # Check if the player is not already in the players dictionary
            if player_id not in players:
                # Add the player to the players dictionary with initial stars set to 0
                players[player_id] = {'team': None, 'stars': 0}

        await ctx.send('Players dictionary updated with all members from the server.')

    except Exception as e:
        error_message = str(e)
        await ctx.send(f'Error: {error_message}')
    

# Replace 'YOUR_BOT_TOKEN' with your actual bot token
bot.run('MTE4MzQ2NTg1MTk5MTYzMzkzMA.GdGNgo.9zgvuc_G55q0ztN7jauLPAfj0g9KhhPzE1hAkk')
