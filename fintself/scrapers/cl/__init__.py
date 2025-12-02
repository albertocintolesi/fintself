# This file makes the 'cl' directory a Python package.
# It exposes scrapers from this country so they can be imported from other modules.

from .banco_chile import BancoChileScraper
from .cencosud import CencosudScraper
from .estado import BancoEstadoScraper
from .santander import SantanderScraper
from .bice import BiceScraper
from .lider_bci import LiderBCIScraper
from .racional import RacionalScraper

__all__ = [
    "BancoChileScraper",
    "BancoEstadoScraper",
    "CencosudScraper",
    "SantanderScraper",
    "BiceScraper",
    "LiderBCIScraper",
    "RacionalScraper"
]
