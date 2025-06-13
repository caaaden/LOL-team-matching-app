# utils.py
import random
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from models import Player, Position, Tier, Match, TeamAssignment
from itertools import combinations, permutations
import math

# 고정된 라인 순서
POSITIONS_ORDER = [Position.TOP, Position.JUNGLE, Position.MID, Position.ADC, Position.SUPPORT]


def calculate_tier_score(tier: str, division: int, lp: int = 0) -> float:
    # ... (이전과 동일)
    base_scores = {
        "IRON": 0, "BRONZE": 400, "SILVER": 800, "GOLD": 1200,
        "PLATINUM": 1600, "EMERALD": 2000, "DIAMOND": 2400,
        "MASTER": 2800, "GRANDMASTER": 2900, "CHALLENGER": 3000
    }
    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
        return base_scores[tier] + division
    division_value = (4 - division) * 100
    lp_value = lp
    return base_scores[tier] + division_value + lp_value


def get_player_position_fit_score(player: Player, target_position: Position) -> int:
    # ... (이전과 동일)
    score = 0
    if player.position == target_position:
        score = 100
    elif player.sub_position and player.sub_position == target_position:
        score = 70
    elif player.position == Position.ALL:
        score = 40
    elif player.sub_position and player.sub_position == Position.ALL:
        score = 20
    return score


def find_best_lineup(team_players: List[Player]) -> Tuple[List[Player], int, float]:
    # print(f"DEBUG: find_best_lineup 호출됨, 입력 플레이어 수: {len(team_players)}")
    # if team_players:
    #     print(f"DEBUG: find_best_lineup 입력 플레이어 닉네임: {[p.nickname for p in team_players]}")

    best_lineup_players_in_order: List[Player] = []
    max_total_fit_score = -1

    if not team_players or len(team_players) != 5:
        # print(f"DEBUG: find_best_lineup - 플레이어 수가 5명이 아님 ({len(team_players)}명), 빈 결과 반환.")
        return [], 0, 0

    team_avg_tier_score = sum(p.tier_score for p in team_players) / len(team_players) if team_players else 0

    initial_permutation_found = False  # 첫번째 유효한 순열이라도 찾았는지 확인용
    for p_permutation in permutations(team_players, len(POSITIONS_ORDER)):
        if not initial_permutation_found:  # 첫번째 순열을 기본값으로 설정
            best_lineup_players_in_order = list(p_permutation)
            max_total_fit_score = 0  # 기본 적합도
            for i, player_in_pos in enumerate(best_lineup_players_in_order):
                target_pos = POSITIONS_ORDER[i]
                max_total_fit_score += get_player_position_fit_score(player_in_pos, target_pos)
            initial_permutation_found = True

        current_total_fit_score = 0
        for i, player_in_pos in enumerate(p_permutation):
            target_pos = POSITIONS_ORDER[i]
            current_total_fit_score += get_player_position_fit_score(player_in_pos, target_pos)

        if current_total_fit_score > max_total_fit_score:
            max_total_fit_score = current_total_fit_score
            best_lineup_players_in_order = list(p_permutation)

    # if best_lineup_players_in_order:
    #     print(f"DEBUG: find_best_lineup 결과 - 최적 라인업: {[p.nickname for p in best_lineup_players_in_order]}, 적합도: {max_total_fit_score}, 평균티어: {team_avg_tier_score:.2f}")
    # else:
    #     print(f"DEBUG: find_best_lineup - 최적 라인업을 찾지 못함 (플레이어 수: {len(team_players)})")

    return best_lineup_players_in_order, max_total_fit_score, team_avg_tier_score


def balance_teams(players: List[Player]) -> Tuple[List[Player], List[Player]]:
    # print(f"DEBUG: balance_teams 호출됨, 입력 플레이어 수: {len(players)}")
    if len(players) != 10:
        # 이 오류는 main.py에서 이미 걸러져야 함.
        raise ValueError("balance_teams 함수는 정확히 10명의 플레이어가 필요합니다.")

    best_overall_blue_team_ordered: List[Player] = []
    best_overall_red_team_ordered: List[Player] = []
    min_final_balance_metric = float('inf')
    found_at_least_one_valid_split = False

    all_team_combinations = list(combinations(players, 5))

    num_combinations_to_check = math.ceil(len(all_team_combinations) / 2.0)  # 정확히 절반 또는 절반+1
    if not all_team_combinations:  # 플레이어가 5명 미만이면 조합이 안나옴 (이론상 10명이므로 발생 안함)
        # print("DEBUG: balance_teams - 플레이어 조합 생성 불가 (10명 미만 또는 오류)")
        raise ValueError("팀 조합을 생성할 수 없습니다. (플레이어 수 부족 또는 내부 오류)")

    for i in range(num_combinations_to_check):
        blue_candidate_players = list(all_team_combinations[i])
        red_candidate_players = [p for p in players if p not in blue_candidate_players]

        # print(f"DEBUG: balance_teams - 조합 {i+1}: 블루후보 {[p.nickname for p in blue_candidate_players]}, 레드후보 {[p.nickname for p in red_candidate_players]}")

        blue_lineup_ordered, blue_total_fit, blue_avg_tier = find_best_lineup(blue_candidate_players)
        red_lineup_ordered, red_total_fit, red_avg_tier = find_best_lineup(red_candidate_players)

        if not blue_lineup_ordered or not red_lineup_ordered or len(blue_lineup_ordered) != 5 or len(
                red_lineup_ordered) != 5:
            # print(f"DEBUG: balance_teams - 조합 {i+1}에서 유효한 라인업 구성 실패. 건너뜀.")
            continue

        found_at_least_one_valid_split = True  # 유효한 분할 및 라인업을 한 번이라도 찾았음
        tier_score_difference = abs(blue_avg_tier - red_avg_tier)
        current_balance_metric = tier_score_difference / (1 + blue_total_fit + red_total_fit)

        # print(f"DEBUG: balance_teams - 조합 {i+1}: 티어차이={tier_score_difference:.2f}, 적합도합계={blue_total_fit+red_total_fit}, 최종점수={current_balance_metric:.4f}")

        if current_balance_metric < min_final_balance_metric:
            min_final_balance_metric = current_balance_metric
            best_overall_blue_team_ordered = blue_lineup_ordered
            best_overall_red_team_ordered = red_lineup_ordered
            # print(f"DEBUG: balance_teams - 새로운 최적팀 발견 (조합 {i+1})")

    if not found_at_least_one_valid_split:
        # 모든 126개 조합에서 유효한 5:5 라인업을 만들지 못한 경우
        # 이는 find_best_lineup이 항상 5명 결과를 반환하도록 수정하면 발생하지 않아야 함.
        # print("치명적 오류: balance_teams - 어떤 조합으로도 유효한 5:5 라인업을 구성할 수 없었습니다.")
        # 이 경우, 매우 기본적인 분배라도 시도.
        players_sorted_by_tier = sorted(players, key=lambda p: p.tier_score, reverse=True)
        blue_fallback = [players_sorted_by_tier[i] for i in [0, 2, 4, 6, 8]]
        red_fallback = [players_sorted_by_tier[i] for i in [1, 3, 5, 7, 9]]

        # Fallback 팀에 대해서도 라인업 구성 시도
        best_overall_blue_team_ordered, _, _ = find_best_lineup(blue_fallback)
        best_overall_red_team_ordered, _, _ = find_best_lineup(red_fallback)

        if not best_overall_blue_team_ordered or not best_overall_red_team_ordered:
            raise ValueError("Fallback 팀 구성조차 실패했습니다. find_best_lineup 로직을 확인하세요.")
        # print("DEBUG: balance_teams - Fallback 팀 구성 사용됨.")

    # print(f"DEBUG: balance_teams 최종 결과 - 블루: {[p.nickname for p in best_overall_blue_team_ordered]}, 레드: {[p.nickname for p in best_overall_red_team_ordered]}")
    return best_overall_blue_team_ordered, best_overall_red_team_ordered


def distribute_players_to_groups(players: List[Player], group_size: int = 10) -> List[List[Player]]:
    num_players = len(players)
    # print(f"DEBUG: distribute_players_to_groups 호출됨, 전체 플레이어 수: {num_players}, 그룹 크기: {group_size}")

    if num_players == 0:
        # print("DEBUG: distribute_players_to_groups - 플레이어가 없어 빈 그룹 반환.")
        return []
    if num_players % group_size != 0:
        # 이 오류는 main.py에서 이미 걸러져야 함.
        raise ValueError(f"플레이어 수는 {group_size}의 배수여야 합니다. 현재 {num_players}명.")

    num_groups = num_players // group_size
    # print(f"DEBUG: distribute_players_to_groups - 생성할 그룹 수: {num_groups}")

    sorted_players = sorted(players, key=lambda p: p.tier_score, reverse=True)
    # print(f"DEBUG: distribute_players_to_groups - 정렬된 플레이어: {[p.nickname for p in sorted_players]}")

    groups: List[List[Player]] = [[] for _ in range(num_groups)]

    for i, player in enumerate(sorted_players):
        round_num = i // num_groups
        idx_in_round = i % num_groups

        if round_num % 2 == 0:
            group_to_assign_idx = idx_in_round
        else:
            group_to_assign_idx = num_groups - 1 - idx_in_round

        groups[group_to_assign_idx].append(player)
        # print(f"DEBUG: distribute_players_to_groups - 플레이어 {player.nickname} (순위 {i+1}) -> 그룹 {group_to_assign_idx}에 배정")

    # for g_idx, group in enumerate(groups):
    #     print(f"DEBUG: distribute_players_to_groups - 최종 그룹 {g_idx}: {[p.nickname for p in group]}, 크기: {len(group)}")
    #     if len(group) != group_size:
    #         print(f"CRITICAL ERROR: distribute_players_to_groups - 그룹 {g_idx} 크기 불일치!")
    #         # 여기서 로직 오류가 있다면 더 자세히 디버깅 필요

    return groups


def update_team_match_scores(winning_team_side: str, match_id: int, db: Session):
    # ... (이전과 동일)
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        print(f"경고: 매치 ID {match_id}를 찾을 수 없어 점수 업데이트를 건너뜁니다.")
        return False
    if match.is_completed:
        print(f"정보: 매치 ID {match_id}는 이미 결과가 등록되어 점수 업데이트를 건너뜁니다.")
        return False

    winning_team_assignments = db.query(TeamAssignment).filter_by(match_id=match_id, team=winning_team_side).all()
    losing_team_side = "RED" if winning_team_side == "BLUE" else "BLUE"
    losing_team_assignments = db.query(TeamAssignment).filter_by(match_id=match_id, team=losing_team_side).all()

    score_changes = {
        "main_win": 35, "main_lose": -25,
        "sub_win": 30, "sub_lose": -30,
        "other_win": 25, "other_lose": -20,
        "all_pos_win": 30, "all_pos_lose": -30,
    }

    for assignment in winning_team_assignments:
        player = db.query(Player).get(assignment.player_id)
        if not player: continue
        assigned_pos_in_match = assignment.assigned_position
        score_change = 0
        if player.position == Position.ALL:
            score_change = score_changes["all_pos_win"]
        elif player.position == assigned_pos_in_match:
            score_change = score_changes["main_win"]
        elif player.sub_position and player.sub_position == assigned_pos_in_match:
            score_change = score_changes["sub_win"]
        else:
            score_change = score_changes["other_win"]
        player.match_score += score_change
        player.win_count += 1

    for assignment in losing_team_assignments:
        player = db.query(Player).get(assignment.player_id)
        if not player: continue
        assigned_pos_in_match = assignment.assigned_position
        score_change = 0
        if player.position == Position.ALL:
            score_change = score_changes["all_pos_lose"]
        elif player.position == assigned_pos_in_match:
            score_change = score_changes["main_lose"]
        elif player.sub_position and player.sub_position == assigned_pos_in_match:
            score_change = score_changes["sub_lose"]
        else:
            score_change = score_changes["other_lose"]
        player.match_score += score_change
        player.lose_count += 1

    match.winner = winning_team_side
    match.is_completed = True
    db.commit()
    return True