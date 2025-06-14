# utils.py - 방법 A 버전 (PostgreSQL 예약어 충돌 해결)
import random
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from models import Player, Position, Tier, Match, TeamAssignment
from itertools import combinations, permutations
import math

# 고정된 라인 순서
POSITIONS_ORDER = [Position.TOP, Position.JUNGLE, Position.MID, Position.ADC, Position.SUPPORT]


def calculate_tier_score(tier: str, division: int, lp: int = 0) -> float:
    """
    플레이어의 티어, 디비전, LP를 기반으로 점수 계산

    Args:
        tier: 티어 (IRON, BRONZE, SILVER, etc.)
        division: 디비전 (1-4) 또는 마스터 이상일 때는 LP
        lp: LP 점수

    Returns:
        계산된 티어 점수
    """
    base_scores = {
        "IRON": 0, "BRONZE": 400, "SILVER": 800, "GOLD": 1200,
        "PLATINUM": 1600, "EMERALD": 2000, "DIAMOND": 2400,
        "MASTER": 2800, "GRANDMASTER": 2900, "CHALLENGER": 3000
    }

    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
        # 마스터 이상에서는 division이 실제로는 LP를 의미
        return base_scores[tier] + division

    # 일반 티어에서는 디비전과 LP 모두 고려
    division_value = (4 - division) * 100  # 디비전이 높을수록 점수 높음
    lp_value = lp
    return base_scores[tier] + division_value + lp_value


def get_player_position_fit_score(player: Player, target_position: Position) -> int:
    """
    플레이어가 특정 포지션에 얼마나 적합한지 점수 계산

    Args:
        player: 플레이어 객체
        target_position: 배정하려는 포지션

    Returns:
        적합도 점수 (0-100)
    """
    score = 0

    # 주 포지션이 일치하면 최고 점수
    if player.position == target_position:  # 호환성 프로퍼티 사용
        score = 100
    # 부 포지션이 일치하면 높은 점수
    elif player.sub_position and player.sub_position == target_position:
        score = 70
    # 주 포지션이 ALL이면 중간 점수
    elif player.position == Position.ALL:  # 호환성 프로퍼티 사용
        score = 40
    # 부 포지션이 ALL이면 낮은 점수
    elif player.sub_position and player.sub_position == Position.ALL:
        score = 20
    # 그 외에는 0점
    else:
        score = 0

    return score


def find_best_lineup(team_players: List[Player]) -> Tuple[List[Player], int, float]:
    """
    5명의 플레이어를 5개 포지션에 최적으로 배정

    Args:
        team_players: 5명의 플레이어 리스트

    Returns:
        (최적 라인업 순서, 총 적합도 점수, 평균 티어 점수)
    """
    best_lineup_players_in_order: List[Player] = []
    max_total_fit_score = -1

    if not team_players or len(team_players) != 5:
        return [], 0, 0

    team_avg_tier_score = sum(p.tier_score for p in team_players) / len(team_players) if team_players else 0

    initial_permutation_found = False

    # 모든 순열을 시도하여 최적 배정 찾기
    for p_permutation in permutations(team_players, len(POSITIONS_ORDER)):
        if not initial_permutation_found:
            # 첫 번째 순열을 기본값으로 설정
            best_lineup_players_in_order = list(p_permutation)
            max_total_fit_score = 0
            for i, player_in_pos in enumerate(best_lineup_players_in_order):
                target_pos = POSITIONS_ORDER[i]
                max_total_fit_score += get_player_position_fit_score(player_in_pos, target_pos)
            initial_permutation_found = True

        # 현재 순열의 적합도 점수 계산
        current_total_fit_score = 0
        for i, player_in_pos in enumerate(p_permutation):
            target_pos = POSITIONS_ORDER[i]
            current_total_fit_score += get_player_position_fit_score(player_in_pos, target_pos)

        # 더 좋은 순열이 발견되면 업데이트
        if current_total_fit_score > max_total_fit_score:
            max_total_fit_score = current_total_fit_score
            best_lineup_players_in_order = list(p_permutation)

    return best_lineup_players_in_order, max_total_fit_score, team_avg_tier_score


def balance_teams(players: List[Player]) -> Tuple[List[Player], List[Player]]:
    """
    10명의 플레이어를 두 팀으로 균형있게 분배

    Args:
        players: 10명의 플레이어 리스트

    Returns:
        (블루팀 5명, 레드팀 5명) - 각각 포지션 순서대로 정렬됨

    Raises:
        ValueError: 플레이어 수가 10명이 아닌 경우
    """
    if len(players) != 10:
        raise ValueError("balance_teams 함수는 정확히 10명의 플레이어가 필요합니다.")

    best_overall_blue_team_ordered: List[Player] = []
    best_overall_red_team_ordered: List[Player] = []
    min_final_balance_metric = float('inf')
    found_at_least_one_valid_split = False

    # 10명 중 5명을 선택하는 모든 조합 생성
    all_team_combinations = list(combinations(players, 5))
    num_combinations_to_check = math.ceil(len(all_team_combinations) / 2.0)

    if not all_team_combinations:
        raise ValueError("팀 조합을 생성할 수 없습니다. (플레이어 수 부족 또는 내부 오류)")

    # 각 조합에 대해 밸런스 평가
    for i in range(num_combinations_to_check):
        blue_candidate_players = list(all_team_combinations[i])
        red_candidate_players = [p for p in players if p not in blue_candidate_players]

        # 각 팀의 최적 라인업 구성
        blue_lineup_ordered, blue_total_fit, blue_avg_tier = find_best_lineup(blue_candidate_players)
        red_lineup_ordered, red_total_fit, red_avg_tier = find_best_lineup(red_candidate_players)

        if not blue_lineup_ordered or not red_lineup_ordered or len(blue_lineup_ordered) != 5 or len(
                red_lineup_ordered) != 5:
            continue

        found_at_least_one_valid_split = True

        # 밸런스 지표 계산: 티어 차이를 포지션 적합도로 나눔
        tier_score_difference = abs(blue_avg_tier - red_avg_tier)
        current_balance_metric = tier_score_difference / (1 + blue_total_fit + red_total_fit)

        # 최선의 조합 업데이트
        if current_balance_metric < min_final_balance_metric:
            min_final_balance_metric = current_balance_metric
            best_overall_blue_team_ordered = blue_lineup_ordered
            best_overall_red_team_ordered = red_lineup_ordered

    if not found_at_least_one_valid_split:
        # 유효한 분할을 찾지 못한 경우 폴백 로직
        players_sorted_by_tier = sorted(players, key=lambda p: p.tier_score, reverse=True)
        blue_fallback = [players_sorted_by_tier[i] for i in [0, 2, 4, 6, 8]]
        red_fallback = [players_sorted_by_tier[i] for i in [1, 3, 5, 7, 9]]

        best_overall_blue_team_ordered, _, _ = find_best_lineup(blue_fallback)
        best_overall_red_team_ordered, _, _ = find_best_lineup(red_fallback)

        if not best_overall_blue_team_ordered or not best_overall_red_team_ordered:
            raise ValueError("Fallback 팀 구성조차 실패했습니다. find_best_lineup 로직을 확인하세요.")

    return best_overall_blue_team_ordered, best_overall_red_team_ordered


def distribute_players_to_groups(players: List[Player], group_size: int = 10) -> List[List[Player]]:
    """
    다수의 플레이어를 여러 그룹으로 균등하게 분배

    Args:
        players: 전체 플레이어 리스트
        group_size: 각 그룹의 크기 (기본값: 10)

    Returns:
        그룹들의 리스트 (각 그룹은 group_size 만큼의 플레이어 포함)

    Raises:
        ValueError: 플레이어 수가 group_size의 배수가 아닌 경우
    """
    num_players = len(players)

    if num_players == 0:
        return []

    if num_players % group_size != 0:
        raise ValueError(f"플레이어 수는 {group_size}의 배수여야 합니다. 현재 {num_players}명.")

    num_groups = num_players // group_size

    # 티어 점수 순으로 정렬 (높은 점수부터)
    sorted_players = sorted(players, key=lambda p: p.tier_score, reverse=True)

    # 스네이크 드래프트 방식으로 분배
    groups: List[List[Player]] = [[] for _ in range(num_groups)]

    for i, player in enumerate(sorted_players):
        round_num = i // num_groups
        idx_in_round = i % num_groups

        # 짝수 라운드는 순서대로, 홀수 라운드는 역순으로
        if round_num % 2 == 0:
            group_to_assign_idx = idx_in_round
        else:
            group_to_assign_idx = num_groups - 1 - idx_in_round

        groups[group_to_assign_idx].append(player)

    return groups


def update_team_match_scores(winning_team_side: str, match_id: int, db: Session) -> bool:
    """
    매치 결과에 따라 플레이어들의 매치 점수 업데이트

    Args:
        winning_team_side: 승리한 팀 ("BLUE" 또는 "RED")
        match_id: 매치 ID
        db: 데이터베이스 세션

    Returns:
        업데이트 성공 여부
    """
    # 매치 정보 조회
    match = db.query(Match).filter(Match.id == match_id).first()
    if not match:
        print(f"경고: 매치 ID {match_id}를 찾을 수 없어 점수 업데이트를 건너뜁니다.")
        return False

    if match.is_completed:
        print(f"정보: 매치 ID {match_id}는 이미 결과가 등록되어 점수 업데이트를 건너뜁니다.")
        return False

    # 팀 배정 정보 조회
    winning_team_assignments = db.query(TeamAssignment).filter_by(match_id=match_id, team=winning_team_side).all()
    losing_team_side = "RED" if winning_team_side == "BLUE" else "BLUE"
    losing_team_assignments = db.query(TeamAssignment).filter_by(match_id=match_id, team=losing_team_side).all()

    # 점수 변동 규칙 정의
    score_changes = {
        "main_win": 35,  # 주 포지션에서 승리
        "main_lose": -25,  # 주 포지션에서 패배
        "sub_win": 30,  # 부 포지션에서 승리
        "sub_lose": -30,  # 부 포지션에서 패배
        "other_win": 25,  # 비선호 포지션에서 승리
        "other_lose": -20,  # 비선호 포지션에서 패배
        "all_pos_win": 30,  # ALL 포지션 플레이어 승리
        "all_pos_lose": -30,  # ALL 포지션 플레이어 패배
    }

    # 승리 팀 점수 업데이트
    for assignment in winning_team_assignments:
        player = db.query(Player).get(assignment.player_id)
        if not player:
            continue

        # 배정된 포지션 확인 (호환성 프로퍼티 사용)
        assigned_pos_in_match = assignment.assigned_position
        score_change = 0

        # 플레이어의 포지션 선호도에 따른 점수 변동 계산 (호환성 프로퍼티 사용)
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

    # 패배 팀 점수 업데이트
    for assignment in losing_team_assignments:
        player = db.query(Player).get(assignment.player_id)
        if not player:
            continue

        # 배정된 포지션 확인 (호환성 프로퍼티 사용)
        assigned_pos_in_match = assignment.assigned_position
        score_change = 0

        # 플레이어의 포지션 선호도에 따른 점수 변동 계산 (호환성 프로퍼티 사용)
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

    # 매치 상태 업데이트
    match.winner = winning_team_side
    match.is_completed = True

    try:
        db.commit()
        return True
    except Exception as e:
        print(f"오류: 매치 점수 업데이트 중 데이터베이스 오류 발생: {e}")
        db.rollback()
        return False